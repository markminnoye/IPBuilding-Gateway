"""Gateway configuration from environment or defaults."""

from __future__ import annotations

import ipaddress
import logging
import os
from dataclasses import dataclass, field

from gateway.installation import InstallationConfig, InstallationError

log = logging.getLogger(__name__)


def _env_truthy(name: str, default: str = "0") -> bool:
    return os.getenv(name, default).lower() in ("1", "true", "yes")


def _default_env_module_ips() -> dict[str, str]:
    """Lab/RE fallback targets when env-default polling is explicitly enabled."""
    return {
        "relay": os.getenv("GATEWAY_RELAY_IP", "10.10.1.30"),
        "dimmer": os.getenv("GATEWAY_DIMMER_IP", "10.10.1.40"),
        "input": os.getenv("GATEWAY_INPUT_IP", "10.10.1.50"),
    }


# ---------------------------------------------------------------------------
# Discovery config
# ---------------------------------------------------------------------------


@dataclass
class DiscoveryConfig:
    """Runtime auto-discovery behaviour (optional, loaded from env)."""

    subnet: str = "10.10.1"
    range_start: int = 0
    range_end: int = 254
    arp_poll_interval_s: float = 30.0
    passive_arp_monitor: bool = True
    auto_discover_on_start: bool = False
    force_discover_on_start: bool = False
    http_timeout_s: float = 2.0
    lock_timeout_s: float = 15.0
    removed_after_n_polls: int = 3

    @classmethod
    def from_env(cls) -> "DiscoveryConfig":
        return cls(
            subnet=os.getenv("GATEWAY_DISCOVERY_SUBNET", "10.10.1"),
            range_start=int(os.getenv("GATEWAY_DISCOVERY_RANGE_START", "0")),
            range_end=int(os.getenv("GATEWAY_DISCOVERY_RANGE_END", "254")),
            arp_poll_interval_s=float(os.getenv("GATEWAY_ARP_POLL_INTERVAL_S", "30.0")),
            passive_arp_monitor=os.getenv("GATEWAY_PASSIVE_ARP_MONITOR", "1").lower()
                in ("1", "true", "yes"),
            auto_discover_on_start=os.getenv("GATEWAY_AUTO_DISCOVER_ON_START", "0").lower()
                in ("1", "true", "yes"),
            force_discover_on_start=os.getenv("GATEWAY_FORCE_DISCOVER_ON_START", "0").lower()
                in ("1", "true", "yes"),
            http_timeout_s=float(os.getenv("GATEWAY_HTTP_TIMEOUT_S", "2.0")),
        )

    def hub_ip_in_subnet(self, hub_ip: str) -> bool:
        """Return True if hub_ip is in the discovery subnet."""
        try:
            hub = ipaddress.ip_address(hub_ip)
            net = ipaddress.ip_network(self.subnet + ".0/24", strict=False)
            return hub in net
        except ValueError:
            return False


# ---------------------------------------------------------------------------
# Gateway config
# ---------------------------------------------------------------------------


@dataclass
class GatewayConfig:
    hub_ip: str = "10.10.1.1"
    hub_port: int = 1001
    rest_host: str = "0.0.0.0"
    rest_port: int = 30200
    rest_shim_enabled: bool = False
    api_host: str = "0.0.0.0"
    api_port: int = 8080
    bind_ip: str = "0.0.0.0"
    reply_timeout_ms: int = 500
    poll_interval_s: float = 2.0
    simulated_mode: bool = False
    log_level: str = "INFO"
    # When True, poll the env-derived relay/dimmer/input IPs when devices.json
    # is missing or failed to load. Off by default in production; enabled
    # automatically in simulated_mode or via GATEWAY_USE_ENV_DEFAULTS=1.
    use_env_defaults: bool = False
    # Human-readable reason devices.json did not load (None when load succeeded).
    installation_load_error: str | None = None
    field_modules: dict[str, str] = field(default_factory=dict)
    # Installation configuration; if set, field_modules is derived from it
    installation: InstallationConfig | None = None
    # Path to the devices.json file on disk. Single source of truth: both the
    # installation loader and the discovery orchestrator consume this.
    devices_file: str = "./devices.json"
    # Discovery configuration (optional; loaded from env)
    discovery: DiscoveryConfig = field(default_factory=DiscoveryConfig)
    # Per-request timeout (seconds) for HTTP calls to field modules
    # (getSysSet / getButtons). 5 s is a comfortable default for
    # IPBuilding controllers on a quiet VLAN; reduce for tighter SLA,
    # raise for slow / loaded networks.
    metadata_timeout_s: float = 5.0

    def __post_init__(self) -> None:
        if (
            not self.field_modules
            and self.installation is None
            and (self.simulated_mode or self.use_env_defaults)
        ):
            object.__setattr__(self, "field_modules", _default_env_module_ips())

    @classmethod
    def from_env(cls) -> GatewayConfig:
        installation: InstallationConfig | None = None
        devices_file = os.getenv("GATEWAY_DEVICES_FILE", "./devices.json")
        load_error: InstallationError | None = None
        try:
            installation = InstallationConfig.load(devices_file)
        except InstallationError as exc:
            load_error = exc

        simulated_mode = _env_truthy("GATEWAY_SIMULATED")
        use_env_defaults = _env_truthy("GATEWAY_USE_ENV_DEFAULTS")
        devices_file_exists = os.path.isfile(devices_file)

        if installation is not None:
            modules = installation.field_modules()
        elif simulated_mode or use_env_defaults:
            modules = _default_env_module_ips()
            reason = "simulated_mode" if simulated_mode else "GATEWAY_USE_ENV_DEFAULTS"
            log.info(
                "Using env default UDP poll targets (%s): %s",
                reason,
                ", ".join(f"{dtype}@{ip}" for dtype, ip in modules.items()),
            )
        else:
            modules = {}
            if not devices_file_exists:
                log.info(
                    "No devices.json at %s — UDP polling disabled until init-sweep "
                    "populates the installation",
                    devices_file,
                )
            elif load_error is not None:
                log.warning(
                    "Failed to load devices.json (%s) — UDP polling disabled until "
                    "discovery succeeds (set GATEWAY_USE_ENV_DEFAULTS=1 for lab IPs): %s",
                    devices_file,
                    load_error,
                )
            else:
                log.info(
                    "devices.json at %s loaded with no modules — UDP polling disabled "
                    "until discovery runs",
                    devices_file,
                )

        discovery = DiscoveryConfig.from_env()
        hub_ip = os.getenv("GATEWAY_HUB_IP", "10.10.1.1")
        metadata_timeout_s = float(os.getenv("GATEWAY_METADATA_TIMEOUT_S", "5.0"))
        if not discovery.hub_ip_in_subnet(hub_ip):
            log.warning(
                "hub_ip %s is outside discovery_subnet %s — "
                "passive ARP monitor may not detect this hub on the field bus",
                hub_ip,
                discovery.subnet,
            )

        return cls(
            hub_ip=hub_ip,
            hub_port=int(os.getenv("GATEWAY_HUB_PORT", "1001")),
            rest_host=os.getenv("GATEWAY_REST_HOST", "0.0.0.0"),
            rest_port=int(os.getenv("GATEWAY_REST_PORT", "30200")),
            rest_shim_enabled=os.getenv("GATEWAY_REST_SHIM_ENABLED", "0").lower() in ("1", "true", "yes"),
            api_host=os.getenv("GATEWAY_API_HOST", "0.0.0.0"),
            api_port=int(os.getenv("GATEWAY_API_PORT", "8080")),
            bind_ip=os.getenv("GATEWAY_BIND_IP", "0.0.0.0"),
            reply_timeout_ms=int(os.getenv("GATEWAY_REPLY_TIMEOUT_MS", "500")),
            poll_interval_s=float(os.getenv("GATEWAY_POLL_INTERVAL", "2.0")),
            simulated_mode=simulated_mode,
            log_level=os.getenv("GATEWAY_LOG_LEVEL", "INFO").upper(),
            use_env_defaults=use_env_defaults,
            installation_load_error=(
                str(load_error)
                if load_error is not None and devices_file_exists
                else None
            ),
            field_modules=modules,
            installation=installation,
            devices_file=devices_file,
            discovery=discovery,
            metadata_timeout_s=metadata_timeout_s,
        )
