"""Home Assistant discovery advertiser.

Registers the gateway on the local network so the
``ha-ipbuilding-gateway`` companion can pick it up under
*Settings -> Devices & Services -> Discovered*.

Two parallel channels are used (the Music Assistant pattern):

1. **Zeroconf / mDNS** — broadcasts ``_ipbuilding-gateway._tcp.local.``
   on the LAN. Works for standalone Docker / Pi deployments.
2. **Home Assistant Supervisor** — ``POST http://supervisor/discovery``
   with ``service: ha_ipbuilding_gateway``. Works on HA OS / Supervised
   where the add-on runs alongside Home Assistant.

When running as a Supervisor add-on, the Zeroconf TXT record carries
``homeassistant_addon=true`` so the companion can deduplicate the two
flows (``async_step_zeroconf`` aborts with ``already_discovered_addon``).
"""

from __future__ import annotations

import asyncio
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
DISCOVERY_SCHEMA_VERSION = 1


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


def _pick_publish_ip(api_host: str) -> str:
    """Choose a sensible IPv4 address to advertise in ``base_url``.

    Prefers an explicit LAN address when bound to ``0.0.0.0`` (use a
    UDP-connect trick that does not actually send packets); falls back
    to ``127.0.0.1`` for the Supervisor / localhost case.
    """
    if api_host not in ("", "0.0.0.0", "::"):
        return api_host

    if _running_as_hass_addon():
        # Add-on: companion connects via host_network / 127.0.0.1.
        return "127.0.0.1"

    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as sock:
            sock.connect(("8.8.8.8", 80))
            return sock.getsockname()[0]
    except OSError:
        return "127.0.0.1"


def _build_txt_properties(
    instance_id: str,
    base_url: str,
    addon: bool,
) -> dict[str, str]:
    """Build Zeroconf TXT properties. All values are strings (RFC 6763)."""
    return {
        "instance_id": instance_id,
        "version": __version__,
        "base_url": base_url,
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
        self._base_url = f"http://{self._publish_ip}:{config.api_port}"

        self._aiozc: AsyncZeroconf | None = None
        self._service_info: AsyncServiceInfo | None = None

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
            self._instance_id, self._base_url, self._is_addon
        )

    # ------------------------------------------------------------------
    # Lifecycle
    # ------------------------------------------------------------------

    async def start(self) -> None:
        if not self._cfg.enabled:
            log.info("HA discovery disabled (GATEWAY_HA_DISCOVERY_ENABLED=0)")
            return

        log.info(
            "Starting HA discovery  instance_id=%s  base_url=%s  addon=%s",
            self._instance_id,
            self._base_url,
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

    async def _start_zeroconf(self) -> None:
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
        # #region agent log (debug fb376d hypothesisId=B)
        import json as _json, time as _time
        _tok = os.environ.get("SUPERVISOR_TOKEN")
        _log_path = "/config/debug-fb376d.log"
        try:
            with open(_log_path, "a", encoding="utf-8") as _f:
                _f.write(_json.dumps({
                    "sessionId": "fb376d",
                    "runId": "initial",
                    "hypothesisId": "B",
                    "location": "gateway/ha_discovery.py:_start_hassio",
                    "message": "SUPERVISOR_TOKEN presence check",
                    "data": {
                        "has_token": bool(_tok),
                        "token_length": len(_tok) if _tok else 0,
                        "gateway_version": __version__,
                    },
                    "timestamp": int(_time.time() * 1000),
                }) + "\n")
        except Exception:
            pass
        # #endregion agent log
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
                "host": "127.0.0.1",
                "port": self._cfg.api_port,
            },
        }
        try:
            async with self._http.post(
                "http://supervisor/discovery",
                json=payload,
                timeout=aiohttp.ClientTimeout(total=10),
            ) as resp:
                # #region agent log (debug fb376d hypothesisId=C)
                import json as _json, time as _time
                _log_path = "/config/debug-fb376d.log"
                try:
                    with open(_log_path, "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({
                            "sessionId": "fb376d",
                            "runId": "initial",
                            "hypothesisId": "C",
                            "location": "gateway/ha_discovery.py:_hassio_announce_once",
                            "message": "Supervisor POST response",
                            "data": {
                                "status": resp.status,
                                "service_key": payload["service"],
                                "config_host": payload["config"]["host"],
                                "config_port": payload["config"]["port"],
                                "content_type": resp.headers.get("Content-Type", ""),
                            },
                            "timestamp": int(_time.time() * 1000),
                        }) + "\n")
                except Exception:
                    pass
                # #endregion agent log
                if resp.status != 200:
                    log.warning(
                        "HassIO discovery POST failed: HTTP %d", resp.status
                    )
                    return None
                data: dict[str, Any] = await resp.json()
                uuid_str = data.get("data", {}).get("uuid")
                # #region agent log (debug fb376d hypothesisId=C success)
                try:
                    with open(_log_path, "a", encoding="utf-8") as _f:
                        _f.write(_json.dumps({
                            "sessionId": "fb376d",
                            "runId": "initial",
                            "hypothesisId": "C",
                            "location": "gateway/ha_discovery.py:_hassio_announce_once:ok",
                            "message": "Supervisor POST 200 — uuid accepted",
                            "data": {
                                "uuid_present": bool(uuid_str),
                                "uuid_length": len(uuid_str) if uuid_str else 0,
                                "response_keys": list(data.keys()) if isinstance(data, dict) else None,
                            },
                            "timestamp": int(_time.time() * 1000),
                        }) + "\n")
                except Exception:
                    pass
                # #endregion agent log
                log.info("HassIO discovery announced: uuid=%s", uuid_str)
                return uuid_str
        except (aiohttp.ClientError, asyncio.TimeoutError) as exc:
            log.warning("HassIO discovery POST error: %s", exc)
            return None
        except json.JSONDecodeError as exc:
            log.warning("HassIO discovery returned non-JSON: %s", exc)
            return None
