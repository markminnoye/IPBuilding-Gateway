"""Home Assistant discovery advertiser.

Registers the gateway on the local network so the
``ha-ipbuilding-gateway`` companion can pick it up under
*Settings -> Devices & Services -> Discovered*.

Two parallel channels are used (the Music Assistant pattern):

1. **Zeroconf / mDNS** — broadcasts ``_ipbgw._tcp.local.`` on the LAN.
   In add-on mode the announced address is the host's LAN address, never
   loopback. Other computers (and the companion, which also listens for
   this record) can then open the API. ``host_network`` means that LAN
   address is the same listener as the add-on.
2. **Home Assistant Supervisor** — ``POST http://supervisor/discovery``
   with ``service: ha_ipbuilding_gateway``. The payload host stays
   ``127.0.0.1`` so the companion on this Home Assistant machine keeps
   its existing local connection.

The Zeroconf TXT record still carries ``homeassistant_addon=true`` when
the gateway runs as an add-on. The companion uses that flag as metadata;
it connects to the address in the mDNS record.
"""

from __future__ import annotations

import asyncio
import ipaddress
import json
import logging
import os
import socket
import uuid
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import aiohttp
from zeroconf.asyncio import AsyncServiceInfo, AsyncZeroconf

from gateway import __version__
from gateway.config import GatewayConfig

log = logging.getLogger(__name__)

#: Zeroconf service type — must match the companion's ``manifest.json``
#: ``"zeroconf"`` entry. Per RFC 6763 §7.2 the leading label (after the
#: underscore) must be ≤ 15 bytes; ``ipbuilding-gateway`` is 18 bytes and
#: is rejected by zeroconf's strict validator.
SERVICE_TYPE = "_ipbgw._tcp.local."

#: Discovery payload schema version. Bump when TXT record format changes
#: in a way the companion needs to react to.
#: v1: instance_id, version, base_url, homeassistant_addon, schema_version
#: v2: + sw, mac, host, port (Shelly-style: explicit host/port + sw alias of version)
DISCOVERY_SCHEMA_VERSION = 2


@dataclass
class HaDiscoveryConfig:
    """Settings for the HA discovery advertiser.

    Mirrors the options exposed in the add-on's ``config.yaml`` so
    operators can disable either channel independently.
    """

    enabled: bool = True
    zeroconf_enabled: bool = True
    hassio_enabled: bool = True
    data_dir: str = "/data"
    api_host: str = "0.0.0.0"
    api_port: int = 8080

    @classmethod
    def from_env(cls) -> "HaDiscoveryConfig":
        return cls(
            enabled=os.getenv("GATEWAY_HA_DISCOVERY_ENABLED", "1").lower()
            in ("1", "true", "yes"),
            zeroconf_enabled=os.getenv("GATEWAY_HA_DISCOVERY_ZEROCONF", "1").lower()
            in ("1", "true", "yes"),
            hassio_enabled=os.getenv("GATEWAY_HA_DISCOVERY_HASSIO", "1").lower()
            in ("1", "true", "yes"),
            data_dir=os.getenv("GATEWAY_DATA_DIR", "/data"),
            api_host=os.getenv("GATEWAY_API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("GATEWAY_API_PORT", "8080")),
        )

    @classmethod
    def from_gateway_config(cls, cfg: GatewayConfig) -> "HaDiscoveryConfig":
        """Build from a fully-loaded :class:`GatewayConfig`."""
        return cls(
            enabled=True,
            zeroconf_enabled=True,
            hassio_enabled=True,
            data_dir=str(Path(cfg.devices_file).parent or "."),
            api_host=cfg.api_host,
            api_port=cfg.api_port,
        )


def _running_as_hass_addon() -> bool:
    """Return True if the gateway is running under Home Assistant Supervisor."""
    return bool(os.environ.get("SUPERVISOR_TOKEN"))


def _load_or_create_instance_id(data_dir: str) -> str:
    """Return a stable UUID for this gateway install.

    Persisted to ``{data_dir}/instance_id`` so the companion can build
    a deterministic ``unique_id`` for both zeroconf and manual config
    flows. Generated once on first start.
    """
    path = Path(data_dir) / "instance_id"
    try:
        if path.exists():
            value = path.read_text(encoding="utf-8").strip()
            if value:
                return value
    except OSError as exc:
        log.warning("Could not read %s: %s — generating new instance id", path, exc)

    new_id = uuid.uuid4().hex
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(new_id, encoding="utf-8")
    except OSError as exc:
        log.warning("Could not persist instance id to %s: %s", path, exc)
    return new_id


# Documentation address used only as a UDP route probe. The kernel picks
# the source address of the default route; no packet is sent.
_ROUTE_PROBE_IPV4 = "192.0.2.1"
_SUPERVISOR_NETWORK_INFO = "http://supervisor/network/info"


def _is_publishable_ipv4(value: str) -> bool:
    """True when ``value`` is an IPv4 address another LAN host can open.

    Loopback, unspecified, multicast, and link-local addresses are refused.
    Private and documentation ranges stay allowed: those are LAN addresses.
    """
    try:
        addr = ipaddress.IPv4Address(value)
    except (ipaddress.AddressValueError, ValueError):
        return False
    return not (
        addr.is_loopback
        or addr.is_unspecified
        or addr.is_multicast
        or addr.is_link_local
    )


def _default_route_ipv4() -> str | None:
    """IPv4 address of the interface that owns the default route."""
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect((_ROUTE_PROBE_IPV4, 80))
            ip = sock.getsockname()[0]
    except OSError:
        return None
    if _is_publishable_ipv4(ip):
        return ip
    return None


def _pick_publish_ip(api_host: str) -> str | None:
    """Choose an IPv4 address to advertise, without talking to Supervisor.

    An explicit bind address is used as-is. Add-on mode with a wildcard
    bind returns ``None`` so startup can ask Supervisor for the host LAN
    address. Standalone mode uses the default-route address and, if that
    fails, loopback (there is no Supervisor API to ask).
    """
    if api_host not in ("", "0.0.0.0", "::"):
        return api_host

    if _running_as_hass_addon():
        return None

    return _default_route_ipv4() or "127.0.0.1"


def _ipv4_hosts(raw: object) -> list[str]:
    """Publishable IPv4 hosts from a string, a CIDR, or a list of those."""
    items: list[object]
    if isinstance(raw, str):
        items = [raw]
    elif isinstance(raw, list):
        items = list(raw)
    else:
        return []
    hosts: list[str] = []
    for item in items:
        host = str(item).split("/", 1)[0].strip()
        if _is_publishable_ipv4(host):
            hosts.append(host)
    return hosts


def _addresses_from_interface(iface: dict[str, Any]) -> list[str]:
    """IPv4 hosts on one Supervisor interface record.

    Accepts the current list shape (``ipv4.address``) and the older
    ``ip_address`` field.
    """
    hosts: list[str] = []
    ipv4 = iface.get("ipv4")
    if isinstance(ipv4, dict):
        hosts.extend(_ipv4_hosts(ipv4.get("address")))
    hosts.extend(_ipv4_hosts(iface.get("ip_address")))
    return hosts


def _skip_interface(name: str) -> bool:
    lowered = name.lower()
    if lowered in {"lo", "loopback"}:
        return True
    return lowered.startswith(("docker", "veth", "hassio", "br-"))


def _interface_has_gateway(iface: dict[str, Any]) -> bool:
    ipv4 = iface.get("ipv4")
    if isinstance(ipv4, dict) and ipv4.get("gateway"):
        return True
    return bool(iface.get("gateway"))


def _normalize_interfaces(payload: dict[str, Any]) -> list[dict[str, Any]]:
    data = payload.get("data") if isinstance(payload.get("data"), dict) else payload
    if not isinstance(data, dict):
        return []
    interfaces = data.get("interfaces")
    if isinstance(interfaces, list):
        return [item for item in interfaces if isinstance(item, dict)]
    if isinstance(interfaces, dict):
        normalized: list[dict[str, Any]] = []
        for name, info in interfaces.items():
            if not isinstance(info, dict):
                continue
            item = dict(info)
            item.setdefault("interface", name)
            normalized.append(item)
        return normalized
    return []


def _pick_ipv4_from_network_info(payload: dict[str, Any]) -> str | None:
    """Host LAN address from a Supervisor ``/network/info`` body.

    Prefers the primary interface, then an interface that has a gateway,
    then any other connected interface. Docker, hassio, and loopback
    interfaces are ignored, and so is ``127.0.0.1``.
    """
    usable: list[dict[str, Any]] = []
    for iface in _normalize_interfaces(payload):
        name = str(iface.get("interface") or "")
        if _skip_interface(name):
            continue
        if iface.get("enabled") is False or iface.get("connected") is False:
            continue
        if not _addresses_from_interface(iface):
            continue
        usable.append(iface)

    groups = (
        [iface for iface in usable if iface.get("primary") is True],
        [iface for iface in usable if _interface_has_gateway(iface)],
        usable,
    )
    for group in groups:
        for iface in group:
            hosts = _addresses_from_interface(iface)
            if hosts:
                return hosts[0]
    return None


async def _fetch_supervisor_network_info() -> dict[str, Any] | None:
    """GET Supervisor ``/network/info``. ``None`` when it cannot be read."""
    token = os.environ.get("SUPERVISOR_TOKEN")
    if not token:
        return None
    try:
        async with aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {token}"}
        ) as http:
            async with http.get(
                _SUPERVISOR_NETWORK_INFO,
                timeout=aiohttp.ClientTimeout(total=5),
            ) as resp:
                if resp.status != 200:
                    log.warning(
                        "Supervisor /network/info failed: HTTP %s", resp.status
                    )
                    return None
                payload = await resp.json()
    except (aiohttp.ClientError, asyncio.TimeoutError, json.JSONDecodeError) as exc:
        log.warning("Supervisor /network/info error: %s", exc)
        return None
    if not isinstance(payload, dict):
        log.warning("Supervisor /network/info returned an unexpected body")
        return None
    return payload


def _parse_host_port(base_url: str) -> tuple[str, str]:
    """Extract host and port from a ``http://host:port`` base URL.

    Falls back to ``("127.0.0.1", "8080")`` when the URL cannot be parsed,
    which keeps the TXT record well-formed even if the add-on options are
    misconfigured.
    """
    from urllib.parse import urlparse

    parsed = urlparse(base_url)
    host = parsed.hostname or "127.0.0.1"
    port = str(parsed.port or 8080)
    return host, port


def _read_interface_mac() -> str:
    """Best-effort MAC of the LAN-facing interface.

    Falls back to ``uuid.getnode()`` (which on Linux reads the first
    interface MAC) and finally to an empty string. Returns the
    colon-separated lower-case form used by HA's device registry
    (``homeassistant.helpers.device_registry.format_mac``).
    """
    try:
        mac_hex = uuid.getnode()
        if (mac_hex >> 40) % 2 == 0:  # locally-administered bit unset → real MAC
            mac = ":".join(f"{(mac_hex >> (8 * i)) & 0xFF:02x}" for i in range(6))
            return mac
    except Exception:
        pass
    return ""


def _build_txt_properties(
    instance_id: str,
    base_url: str,
    addon: bool,
    mac: str = "",
) -> dict[str, str]:
    """Build Zeroconf TXT properties. All values are strings (RFC 6763).

    Field set (schema v2):

    - ``instance_id``: stable UUID per gateway install (used as HA unique_id)
    - ``version``/``sw``: gateway semver (kept both for back-compat)
    - ``host``/``port``: where the companion should connect
    - ``base_url``: convenience (``http://host:port``) for older clients
    - ``mac``: colon-separated MAC of the LAN-facing interface; empty
      when unavailable (e.g. add-on with host_network)
    - ``homeassistant_addon``: "true" when running under Supervisor
    - ``schema_version``: integer as string; the companion uses this to
      switch between TXT layouts
    """
    host, port = _parse_host_port(base_url)
    return {
        "instance_id": instance_id,
        "version": __version__,
        "sw": __version__,
        "host": host,
        "port": port,
        "base_url": base_url,
        "mac": mac,
        "homeassistant_addon": "true" if addon else "false",
        "schema_version": str(DISCOVERY_SCHEMA_VERSION),
    }


class HaDiscoveryAdvertiser:
    """Publishes the gateway to Home Assistant over both discovery channels."""

    def __init__(
        self,
        config: HaDiscoveryConfig,
        instance_id: str | None = None,
    ) -> None:
        self._cfg = config
        self._instance_id = instance_id or _load_or_create_instance_id(config.data_dir)
        self._is_addon = _running_as_hass_addon()
        self._publish_ip = _pick_publish_ip(config.api_host)
        if self._is_addon and not _is_publishable_ipv4(self._publish_ip or ""):
            # Resolved in start() from Supervisor /network/info. Never keep
            # a loopback placeholder that could be announced on the LAN.
            self._publish_ip = None
        self._base_url = (
            f"http://{self._publish_ip}:{config.api_port}" if self._publish_ip else ""
        )

        self._aiozc: AsyncZeroconf | None = None
        self._service_info: AsyncServiceInfo | None = None

        # Best-effort LAN MAC; empty when running under Supervisor (the
        # add-on does not own a unique interface).
        self._mac = "" if self._is_addon else _read_interface_mac()

        # HassIO state
        self._hassio_uuid: str | None = None
        self._hassio_task: asyncio.Task[None] | None = None
        self._http: aiohttp.ClientSession | None = None

    # ------------------------------------------------------------------
    # Public properties
    # ------------------------------------------------------------------

    @property
    def instance_id(self) -> str:
        return self._instance_id

    @property
    def base_url(self) -> str:
        return self._base_url

    @property
    def is_addon(self) -> bool:
        return self._is_addon

    @property
    def txt_properties(self) -> dict[str, str]:
        return _build_txt_properties(
            self._instance_id, self._base_url, self._is_addon, mac=self._mac
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self._cfg.enabled:
            log.info("HA discovery disabled (GATEWAY_HA_DISCOVERY_ENABLED=0)")
            return

        if (
            self._cfg.zeroconf_enabled
            and self._is_addon
            and not _is_publishable_ipv4(self._publish_ip or "")
        ):
            await self._resolve_addon_publish_ip()

        log.info(
            "Starting HA discovery  instance_id=%s  base_url=%s  addon=%s",
            self._instance_id,
            self._base_url or "(not announced)",
            self._is_addon,
        )

        if self._cfg.zeroconf_enabled:
            await self._start_zeroconf()
        if self._cfg.hassio_enabled and self._is_addon:
            await self._start_hassio()

    async def stop(self) -> None:
        log.info("Stopping HA discovery")
        if self._hassio_task is not None:
            self._hassio_task.cancel()
            try:
                await self._hassio_task
            except (asyncio.CancelledError, Exception):
                pass
            self._hassio_task = None

        if self._service_info is not None and self._aiozc is not None:
            try:
                await self._aiozc.async_unregister_service(self._service_info)
            except Exception as exc:
                log.warning("Zeroconf unregister failed: %s", exc)
            self._service_info = None

        if self._aiozc is not None:
            try:
                await self._aiozc.async_close()
            except Exception as exc:
                log.warning("Zeroconf close failed: %s", exc)
            self._aiozc = None

        if self._http is not None:
            try:
                if self._hassio_uuid:
                    await self._http.delete(
                        f"http://supervisor/discovery/{self._hassio_uuid}"
                    )
            except Exception as exc:
                log.debug("HassIO discovery delete failed: %s", exc)
            try:
                await self._http.close()
            except Exception as exc:
                log.debug("HTTP session close failed: %s", exc)
            self._http = None

    # ------------------------------------------------------------------
    # Zeroconf
    # ------------------------------------------------------------------

    async def _resolve_addon_publish_ip(self) -> None:
        """Set the add-on mDNS address from Supervisor, then the default route.

        When neither source yields a LAN address, leave the advertiser
        without a publish address so Zeroconf is not registered.
        """
        payload = await _fetch_supervisor_network_info()
        ip = _pick_ipv4_from_network_info(payload) if payload else None
        source = "supervisor"
        if ip is None:
            ip = _default_route_ipv4()
            source = "default route"
        if ip is None:
            self._publish_ip = None
            self._base_url = ""
            log.warning(
                "Zeroconf announcement skipped: no LAN IPv4 address in "
                "add-on mode. Refusing to publish 127.0.0.1. Supervisor "
                "/network/info and the default route both failed."
            )
            return
        self._publish_ip = ip
        self._base_url = f"http://{ip}:{self._cfg.api_port}"
        log.info("Add-on Zeroconf address from %s: %s", source, ip)

    async def _start_zeroconf(self) -> None:
        if self._is_addon and not _is_publishable_ipv4(self._publish_ip or ""):
            return
        if not self._publish_ip:
            return
        # Use dual-stack mDNS (IPv4 + IPv6) so the broadcast reaches both
        # legacy IPv4-only clients (older HA instances, some
        # Bonjour implementations) and modern IPv6 stacks. Forcing
        # V4Only occasionally trips macOS's dns-sd CLI on certain LAN
        # configurations — a quirk we've hit in dev.
        self._aiozc = AsyncZeroconf()
        # The mDNS *server* label (per RFC 6762 §6.7) is at most 15 bytes.
        # Keep a short, stable hostname here — the unique instance id lives
        # in TXT (`instance_id`), not in the host label.
        server_label = "ipbgw.local."
        # Service instance names (the `<label>._ipbgw._tcp.local.` part)
        # allow up to 63 bytes per RFC 6763 §7.2, so we can include a
        # short slice of the instance id for human-readable discovery.
        short_id = self._instance_id[:8]
        service_name = f"ipbgw-{short_id}.{SERVICE_TYPE}"
        self._service_info = AsyncServiceInfo(
            SERVICE_TYPE,
            name=service_name,
            addresses=[socket.inet_aton(self._publish_ip)],
            port=self._cfg.api_port,
            properties=self.txt_properties,
            server=server_label,
        )
        try:
            await self._aiozc.async_register_service(self._service_info)
            log.info(
                "Zeroconf registered: service_name=%s server=%s port=%d "
                "publish_ip=%s has_host_in_properties=%s has_port_in_properties=%s",
                service_name,
                server_label,
                self._cfg.api_port,
                self._publish_ip,
                "host" in self.txt_properties,
                "port" in self.txt_properties,
            )
        except Exception as exc:
            log.warning("Zeroconf registration failed: %s", exc)
            self._service_info = None

    # ------------------------------------------------------------------
    # HassIO supervisor
    # ------------------------------------------------------------------

    async def _start_hassio(self) -> None:
        if not os.environ.get("SUPERVISOR_TOKEN"):
            log.info("HassIO discovery skipped (no SUPERVISOR_TOKEN)")
            return
        self._http = aiohttp.ClientSession(
            headers={"Authorization": f"Bearer {os.environ['SUPERVISOR_TOKEN']}"}
        )
        self._hassio_task = asyncio.create_task(
            self._hassio_announce_loop(), name="ha-discovery-hassio"
        )

    async def _hassio_announce_loop(self) -> None:
        """Announce to Supervisor, with periodic re-announce + retry on failure."""
        backoff = 2.0
        while True:
            try:
                uuid_str = await self._hassio_announce_once()
                if uuid_str:
                    self._hassio_uuid = uuid_str
                    backoff = 2.0
                    # Re-announce every 5 minutes; Supervisor considers
                    # entries stale after a few minutes of silence.
                    await asyncio.sleep(300)
                else:
                    await asyncio.sleep(backoff)
                    backoff = min(backoff * 2, 60.0)
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                log.warning("HassIO announce loop error: %s", exc)
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _hassio_announce_once(self) -> str | None:
        assert self._http is not None
        payload = {
            "service": "ha_ipbuilding_gateway",
            "config": {
                # Local discovery for the companion on this Home Assistant
                # host. host_network makes 127.0.0.1 reach the add-on.
                # The LAN address is announced only via Zeroconf.
                "host": "127.0.0.1",
                "port": self._cfg.api_port,
                "instance_id": self._instance_id,
            },
        }
        try:
            async with self._http.post(
                "http://supervisor/discovery",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                if resp.status != 200:
                    log.warning(
                        "HassIO discovery POST failed: HTTP %d", resp.status
                    )
                    return None
                data: dict[str, Any] = await resp.json()
                uuid_str = data.get("data", {}).get("uuid")
                log.info("HassIO discovery announced: uuid=%s", uuid_str)
                return uuid_str
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("HassIO discovery POST error: %s", exc)
            return None
        except json.JSONDecodeError as exc:
            log.warning("HassIO discovery returned non-JSON: %s", exc)
            return None
