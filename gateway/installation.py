"""Installation configuration from devices.json.

Parses the installation-specific mapping of component IDs to
module IPs and channels, and provides lookups used by RESTShim
and the registry wiring in main.py.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass, field
from pathlib import Path

from gateway.types import DeviceType


class InstallationError(Exception):
    """Raised when devices.json is missing, invalid, or inconsistent."""


@dataclass
class ChannelConfig:
    """A single channel on a field module."""

    ch: int
    id: int  # IPBox component ID (unique across all modules)
    description: str = ""
    group: str = ""


@dataclass
class ModuleConfig:
    """A single field module (relay/dimmer/input)."""

    name: str
    ip: str
    type: DeviceType
    channels: list[ChannelConfig] = field(default_factory=list)

    @property
    def ip_decimal(self) -> str:
        """Return the last octet of the IP as an integer (e.g. '30' from '10.10.1.30')."""
        return self.ip.rsplit(".", 1)[-1]


@dataclass
class InstallationConfig:
    """Loaded and validated installation configuration."""

    modules: list[ModuleConfig] = field(default_factory=list)

    # Derived indices
    _id_to_entry: dict[int, tuple[DeviceType, str, int]] = field(default_factory=dict)
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
        seen_ids: set[int] = set()
        modules: list[ModuleConfig] = []
        id_to_entry: dict[int, tuple[DeviceType, str, int]] = {}
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

            channels: list[ChannelConfig] = []
            for ch_entry in mod.get("channels", []):
                ch = ch_entry.get("ch")
                comp_id = ch_entry.get("id")
                if not isinstance(ch, int) or not isinstance(comp_id, int):
                    raise InstallationError(
                        f"Channel missing 'ch' or 'id' int in module {mod_ip}: {ch_entry!r}"
                    )
                if comp_id in seen_ids:
                    raise InstallationError(
                        f"Duplicate component id {comp_id} across modules"
                    )
                seen_ids.add(comp_id)
                channels.append(
                    ChannelConfig(
                        ch=ch,
                        id=comp_id,
                        description=ch_entry.get("description", ""),
                        group=ch_entry.get("group", ""),
                    )
                )
                id_to_entry[comp_id] = (dtype, mod_ip, ch)

            mc = ModuleConfig(
                name=mod.get("name", mod_ip),
                ip=mod_ip,
                type=dtype,
                channels=channels,
            )
            modules.append(mc)
            modules_by_ip[mod_ip] = mc

        inst = cls(modules=modules)
        inst._id_to_entry = id_to_entry
        inst._modules_by_ip = modules_by_ip
        return inst

    def id_to_channel(
        self, comp_id: int
    ) -> tuple[DeviceType, str, int] | None:
        """Look up a component ID. Returns (device_type, module_ip, channel) or None."""
        return self._id_to_entry.get(comp_id)

    def module_by_ip(self, module_ip: str) -> ModuleConfig | None:
        """Return the ModuleConfig for a given IP, or None."""
        return self._modules_by_ip.get(module_ip)

    def field_modules(self) -> dict[str, str]:
        """Return a {type: ip} dict for GatewayConfig.field_modules derivation."""
        result: dict[str, str] = {}
        for mc in self.modules:
            result[mc.type.value] = mc.ip
        return result

    def all_component_ids(self) -> list[int]:
        """All known component IDs in installation order (first seen = first listed)."""
        return list(self._id_to_entry.keys())