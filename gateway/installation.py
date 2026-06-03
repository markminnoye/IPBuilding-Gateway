"""Installation configuration from devices.json.

Parses the installation-specific mapping of field modules to channels,
and provides lookups used by RESTShim and the registry wiring in main.py.

ID model
--------
- ``ipbox_id``  Optional integer per channel — the IPBox component ID
                 (e.g. 547).  Used exclusively by rest_shim.py during the
                 HA-IPBuilding transition.  Will disappear when the shim is
                 retired.
- ``entity_id``  Deterministic string derived from (module_ip, channel):
                 ``"10.10.1.30:0"``.  Never stored; always computed via
                 :func:`make_entity_id`.  The device type is NOT part of the
                 external ID — it is always resolved server-side via
                 :meth:`InstallationConfig.module_by_ip`.  Used by the product
                 API (gateway_api.py) and the companion.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from gateway.types import DeviceType


class InstallationError(Exception):
    """Raised when devices.json is missing, invalid, or inconsistent."""


def make_entity_id(module_ip: str, channel: int) -> str:
    """Derive a stable, fieldbus-native entity ID.

    Format: ``'{module_ip}:{channel}'``
    Example: ``'10.10.1.30:0'``

    The device type is intentionally omitted — it is a module-level attribute
    resolved server-side via :meth:`InstallationConfig.module_by_ip`, never
    supplied by the client.  This prevents type-spoofing.

    This value is **never stored** — it is always computed from the fieldbus
    address.  It is the primary identifier for the open gateway product API.
    """
    return f"{module_ip}:{channel}"


@dataclass
class ChannelConfig:
    """A single channel on a field module."""

    ch: int
    ipbox_id: int | None = None  # IPBox component ID — shim only, optional
    # Northbound fields (from devices.json)
    name: str = ""
    room: str = ""
    semantic_type: str = "light"  # light | fan | cover | switch | plug
    active: bool = True
    max_watt: int = 0

    @property
    def description(self) -> str:
        """Alias for name, for backward compatibility."""
        return self.name

    @property
    def group(self) -> str:
        """Alias for room, for backward compatibility."""
        return self.room


@dataclass
class ModuleConfig:
    """A single field module (relay/dimmer/input)."""

    name: str
    ip: str
    type: DeviceType
    firmware: str = ""  # read via getSysSet during discovery
    channels: list[ChannelConfig] = field(default_factory=list)

    @property
    def ip_decimal(self) -> str:
        """Return the last octet of the IP as an integer (e.g. '30' from '10.10.1.30')."""
        return self.ip.rsplit(".", 1)[-1]


@dataclass
class InstallationConfig:
    """Loaded and validated installation configuration."""

    modules: list[ModuleConfig] = field(default_factory=list)

    # Derived indices — keyed by ipbox_id (IPBox component ID)
    _ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = field(default_factory=dict)
    # module_ip -> ModuleConfig
    _modules_by_ip: dict[str, ModuleConfig] = field(default_factory=dict)

    @classmethod
    def load(
        cls,
        path: str | os.PathLike | None = None,
    ) -> InstallationConfig:
        """Load and validate devices.json from the given path or GATEWAY_DEVICES_FILE env."""
        if path is None:
            path = os.getenv("GATEWAY_DEVICES_FILE", "./devices.json")

        resolved = Path(path).expanduser().resolve()

        if not resolved.exists():
            raise InstallationError(
                f"devices.json not found at {resolved} "
                f"(set GATEWAY_DEVICES_FILE to override)"
            )

        try:
            with open(resolved, encoding="utf-8") as fh:
                raw = json.load(fh)
        except json.JSONDecodeError as exc:
            raise InstallationError(f"devices.json is not valid JSON: {exc}") from exc

        return cls._parse(raw)

    @classmethod
    def _parse(cls, raw: dict) -> InstallationConfig:
        """Parse a devices.json dict into InstallationConfig."""
        seen_ipbox_ids: set[int] = set()
        modules: list[ModuleConfig] = []
        ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = {}
        modules_by_ip: dict[str, ModuleConfig] = {}

        for mod in raw.get("modules", []):
            mod_type_str = mod.get("type", "")
            try:
                dtype = DeviceType(mod_type_str)
            except ValueError:
                raise InstallationError(
                    f"Unknown module type {mod_type_str!r}; "
                    f"expected relay | dimmer | input"
                )

            mod_ip = mod.get("ip", "")
            if not mod_ip:
                raise InstallationError(f"Module missing 'ip' field: {mod!r}")

            if mod_ip in modules_by_ip:
                raise InstallationError(f"Duplicate module IP: {mod_ip}")

            firmware = mod.get("firmware", "")

            channels: list[ChannelConfig] = []
            for ch_entry in mod.get("channels", []):
                ch = ch_entry.get("ch")
                if not isinstance(ch, int):
                    raise InstallationError(
                        f"Channel missing 'ch' int in module {mod_ip}: {ch_entry!r}"
                    )

                ipbox_id: int | None = ch_entry.get("ipbox_id")
                if ipbox_id is not None:
                    if not isinstance(ipbox_id, int):
                        raise InstallationError(
                            f"ipbox_id must be int in module {mod_ip}: {ch_entry!r}"
                        )
                    if ipbox_id in seen_ipbox_ids:
                        raise InstallationError(
                            f"Duplicate component id {ipbox_id} across modules"
                        )
                    seen_ipbox_ids.add(ipbox_id)
                    ipbox_id_to_entry[ipbox_id] = (dtype, mod_ip, ch)

                channels.append(
                    ChannelConfig(
                        ch=ch,
                        ipbox_id=ipbox_id,
                        name=ch_entry.get("name") or ch_entry.get("description") or f"Ch {ch}",
                        room=ch_entry.get("room") or ch_entry.get("group") or "",
                        semantic_type=ch_entry.get("semantic_type", "light"),
                        active=ch_entry.get("active", True),
                        max_watt=ch_entry.get("max_watt", 0),
                    )
                )

            mc = ModuleConfig(
                name=mod.get("name", mod_ip),
                ip=mod_ip,
                type=dtype,
                firmware=firmware,
                channels=channels,
            )
            modules.append(mc)
            modules_by_ip[mod_ip] = mc

        inst = cls(modules=modules)
        inst._ipbox_id_to_entry = ipbox_id_to_entry
        inst._modules_by_ip = modules_by_ip
        return inst

    def make_entity_id(self, module_ip: str, channel: int) -> str:
        """Delegate to module-level :func:`make_entity_id`."""
        return make_entity_id(module_ip, channel)

    def ipbox_id_to_channel(
        self, ipbox_id: int
    ) -> tuple[DeviceType, str, int] | None:
        """Look up a channel by IPBox legacy ID.

        Returns ``(device_type, module_ip, channel)`` or ``None`` if the
        ipbox_id is not known.  Used exclusively by the REST shim.
        """
        return self._ipbox_id_to_entry.get(ipbox_id)

    def module_by_ip(self, module_ip: str) -> ModuleConfig | None:
        """Return the ModuleConfig for a given IP, or None."""
        return self._modules_by_ip.get(module_ip)

    def field_modules(self) -> dict[str, str]:
        """Return a {type: ip} dict for GatewayConfig.field_modules derivation."""
        result: dict[str, str] = {}
        for mc in self.modules:
            result[mc.type.value] = mc.ip
        return result

    def all_ipbox_ids(self) -> list[int]:
        """All known legacy (IPBox component) IDs in installation order."""
        return list(self._ipbox_id_to_entry.keys())
