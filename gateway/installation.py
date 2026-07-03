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
- ``module_id``  Stable module identifier: normalised MAC (lowercase,
                 colon-separated).  Used as the primary key for the
                 ``/api/v1/modules`` resource.  IP can change (DHCP);
                 MAC never does.
"""

from __future__ import annotations

import json
import logging
import os
from dataclasses import dataclass, field
from pathlib import Path

from gateway.types import DeviceType

log = logging.getLogger(__name__)


def _normalize_mac(mac: str) -> str:
    """Normalise a MAC to lowercase colon-separated.

    Handles: ``00:24:77:52:ac:be``, ``0:24:77:52:ac:be``,
    ``00-24-77-52-ac-be``, ``0.24.77.52.ac.be`` (decimal-dot from
    module getSysSet ``mac="0.36.119.82.172.190"``).
    """
    normalized = mac.lower().replace("-", ":").replace(".", ":")
    parts = normalized.split(":")
    return ":".join(f"{int(p, 16):02x}" for p in parts if p)


class InstallationError(Exception):
    """Raised when devices.json is missing, invalid, or inconsistent."""


def make_entity_id(module_ip: str, channel: int) -> str:
    """Derive a stable, fieldbus-native entity ID.

    Format: ``'{module_ip}-{channel}'``
    Example: ``'10.10.1.30-0'``

    The device type is intentionally omitted — it is a module-level attribute
    resolved server-side via :meth:`InstallationConfig.module_by_ip`, never
    supplied by the client.  This prevents type-spoofing.

    This value is **never stored** — it is always computed from the fieldbus
    address.  It is the primary identifier for the open gateway product API.
    """
    return f"{module_ip}-{channel}"


@dataclass
class ChannelConfig:
    """A single channel on a field module."""

    ch: int
    ipbox_id: int | None = None  # IPBox component ID — shim only, optional
    id: str = ""  # Unified device ID (defaulting to {ip}-{ch} or custom slug)
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

    def to_dict(self, *, module_ip: str | None = None) -> dict:
        """Serialize to dict for devices.json.

        The default ``id`` (``{module_ip}-{ch}``) is omitted — only custom
        slugs are persisted. Pass ``module_ip`` when serialising a full
        installation document via :meth:`InstallationConfig.to_dict`.
        """
        d: dict = {
            "ch": self.ch,
            "name": self.name,
            "room": self.room,
            "semantic_type": self.semantic_type,
            "active": self.active,
            "max_watt": self.max_watt,
        }
        if self.ipbox_id is not None:
            d["ipbox_id"] = self.ipbox_id
        if module_ip is not None and self.id and self.id != f"{module_ip}-{self.ch}":
            d["id"] = self.id
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ChannelConfig":
        return cls(
            ch=data["ch"],
            ipbox_id=data.get("ipbox_id"),
            id=data.get("id", ""),
            name=data.get("name", data.get("description", "")),
            room=data.get("room", data.get("group", "")),
            semantic_type=data.get("semantic_type", "light"),
            active=data.get("active", True),
            max_watt=data.get("max_watt", 0),
        )


# Default hold threshold (seconds) when no per-button override is present.
# Matches the IPBox default in `getButtons` (which the IPBox software maps
# to 0.5/1/1.5/2/2.5/3/4/5s — 1.5s is the typical middle).
DEFAULT_BUTTON_HOLD_THRESHOLD_S = 1.5


@dataclass
class ButtonConfig:
    """A single physical button on an IP1100PoE input module.

    Buttons are not channels — they have no entity_id of the form
    `{module_ip}-{ch}`. They are event sources on a module. The gateway
    uses :attr:`hold_threshold_s` to classify press→release timing into
    ``press`` vs ``long_press`` events; the value is normally seeded from
    ``getButtons.func2.holdSeconds`` on the input module (operator-bevestigd
    2026-06-16: dit is dezelfde drempel die IPBox hanteert).
    """

    id: str  # hardware hex, e.g. "2f8185190000df" (14 lowercase hex chars)
    module_id: str = ""  # parent module MAC (stable)
    name: str = ""  # operator-friendly description, default from getButtons.descr
    room: str = ""  # from getButtons.gr
    active: bool = True
    hold_threshold_s: float = DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json."""
        return {
            "id": self.id,
            "module_id": self.module_id,
            "name": self.name,
            "room": self.room,
            "active": self.active,
            "hold_threshold_s": self.hold_threshold_s,
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ButtonConfig":
        return cls(
            id=data["id"],
            module_id=data.get("module_id", ""),
            name=data.get("name", ""),
            room=data.get("room", ""),
            active=data.get("active", True),
            hold_threshold_s=float(
                data.get("hold_threshold_s", DEFAULT_BUTTON_HOLD_THRESHOLD_S)
            ),
        )


@dataclass
class ModuleConfig:
    """A single field module (relay/dimmer/input)."""

    name: str
    ip: str
    type: DeviceType
    firmware: str = ""  # read via getSysSet during discovery
    model: str = ""    # factory product label, e.g. "IP200PoE"; optional
    mac: str = ""      # factory MAC (OUI 00:24:77); normalised lowercase
    channels: list[ChannelConfig] = field(default_factory=list)
    # Runtime-only fields — NOT serialized to devices.json
    last_seen: str | None = None       # ISO timestamp of last ARP/HTTP contact
    last_seen_source: str = ""         # "arp" | "http" | "udp"

    @property
    def module_id(self) -> str:
        """Module identifier: normalised MAC. Alias for mac field."""
        return self.mac

    @property
    def ip_decimal(self) -> str:
        """Return the last octet of the IP as an integer (e.g. '30' from '10.10.1.30')."""
        return self.ip.rsplit(".", 1)[-1]

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json, excluding runtime-only fields."""
        return {
            "name": self.name,
            "ip": self.ip,
            "type": self.type.value,
            "firmware": self.firmware,
            "model": self.model,
            "mac": self.mac,
            "channels": [c.to_dict(module_ip=self.ip) for c in self.channels],
        }

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleConfig":
        """Reconstruct from a devices.json dict entry, skipping runtime fields."""
        return cls(
            name=data.get("name", data.get("ip", "")),
            ip=data["ip"],
            type=DeviceType(data["type"]),
            firmware=data.get("firmware", ""),
            model=data.get("model", ""),
            mac=data.get("mac", ""),
            channels=[ChannelConfig.from_dict(c) for c in data.get("channels", [])],
        )


@dataclass
class InstallationConfig:
    """Loaded and validated installation configuration."""

    modules: list[ModuleConfig] = field(default_factory=list)
    # Physical buttons (IP1100PoE). Authoritative for hold_threshold_s and
    # event routing. Persisted in devices.json under top-level "buttons" key.
    buttons: list[ButtonConfig] = field(default_factory=list)

    # Derived indices — keyed by ipbox_id (IPBox component ID)
    _ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = field(default_factory=dict)
    # module_ip -> ModuleConfig
    _modules_by_ip: dict[str, ModuleConfig] = field(default_factory=dict)
    # module_id (MAC) -> ModuleConfig
    _modules_by_mac: dict[str, ModuleConfig] = field(default_factory=dict)
    # device_id -> (DeviceType, module_ip, channel)
    _device_id_to_entry: dict[str, tuple[DeviceType, str, int]] = field(default_factory=dict)
    # (DeviceType, module_ip, channel) -> device_id
    _entry_to_device_id: dict[tuple[DeviceType, str, int], str] = field(default_factory=dict)
    # button hardware id (lowercase) -> ButtonConfig
    _buttons_by_id: dict[str, ButtonConfig] = field(default_factory=dict)

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
        seen_device_ids: set[str] = set()
        modules: list[ModuleConfig] = []
        buttons: list[ButtonConfig] = []
        ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = {}
        device_id_to_entry: dict[str, tuple[DeviceType, str, int]] = {}
        entry_to_device_id: dict[tuple[DeviceType, str, int], str] = {}
        modules_by_ip: dict[str, ModuleConfig] = {}
        modules_by_mac: dict[str, ModuleConfig] = {}
        buttons_by_id: dict[str, ButtonConfig] = {}

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
            mac_raw = mod.get("mac", "")
            mac_normalised = _normalize_mac(mac_raw) if mac_raw else ""

            if mac_normalised and mac_normalised in modules_by_mac:
                raise InstallationError(f"Duplicate module MAC: {mac_normalised}")

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

                # Read or default the device_id
                device_id = ch_entry.get("id")
                if not device_id:
                    device_id = f"{mod_ip}-{ch}"

                if device_id in seen_device_ids:
                    raise InstallationError(
                        f"Duplicate device id {device_id!r} across modules"
                    )
                seen_device_ids.add(device_id)
                device_id_to_entry[device_id] = (dtype, mod_ip, ch)
                entry_to_device_id[(dtype, mod_ip, ch)] = device_id

                channels.append(
                    ChannelConfig(
                        ch=ch,
                        ipbox_id=ipbox_id,
                        id=device_id,
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
                model=mod.get("model", ""),
                mac=mac_normalised,
                channels=channels,
            )
            modules.append(mc)
            modules_by_ip[mod_ip] = mc
            if mac_normalised:
                modules_by_mac[mac_normalised] = mc

        # Parse top-level "buttons" list. Authoritative for hold_threshold_s
        # and event routing. Module may not have an HTTP cache yet — the
        # gateway seeds / merges these from getButtons at runtime.
        for btn_entry in raw.get("buttons", []):
            btn_id = btn_entry.get("id")
            if not btn_id:
                log.warning("Skipping button entry without id: %r", btn_entry)
                continue
            key = btn_id.lower()
            if key in buttons_by_id:
                raise InstallationError(
                    f"Duplicate button id {btn_id!r}"
                )
            btn = ButtonConfig.from_dict(btn_entry)
            buttons.append(btn)
            buttons_by_id[key] = btn

        inst = cls(modules=modules, buttons=buttons)
        inst._ipbox_id_to_entry = ipbox_id_to_entry
        inst._modules_by_ip = modules_by_ip
        inst._modules_by_mac = modules_by_mac
        inst._device_id_to_entry = device_id_to_entry
        inst._entry_to_device_id = entry_to_device_id
        inst._buttons_by_id = buttons_by_id
        return inst

    def device_id_to_entry(
        self, device_id: str
    ) -> tuple[DeviceType, str, int] | None:
        """Look up a channel by unified device ID.

        Returns ``(device_type, module_ip, channel)`` or ``None``.
        """
        return self._device_id_to_entry.get(device_id)

    def entry_to_device_id(
        self, device_type: DeviceType, module_ip: str, channel: int
    ) -> str | None:
        """Look up the unified device ID for a given channel entry.

        Returns the device ID string or ``None``.
        """
        return self._entry_to_device_id.get((device_type, module_ip, channel))

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

    def module_by_mac(self, module_mac: str) -> ModuleConfig | None:
        """Return the ModuleConfig for a given normalised MAC, or None."""
        return self._modules_by_mac.get(module_mac.lower())

    def field_modules(self) -> dict[str, str]:
        """Return a {type: ip} dict for GatewayConfig.field_modules derivation."""
        result: dict[str, str] = {}
        for mc in self.modules:
            result[mc.type.value] = mc.ip
        return result

    def all_ipbox_ids(self) -> list[int]:
        """All known legacy (IPBox component) IDs in installation order."""
        return list(self._ipbox_id_to_entry.keys())

    def button_by_id(self, button_id: str) -> ButtonConfig | None:
        """Look up a button by hardware id (case-insensitive). Returns None if unknown."""
        if not button_id:
            return None
        return self._buttons_by_id.get(button_id.lower())

    def button_threshold(self, button_id: str) -> float:
        """Return the hold threshold (seconds) for a button.

        Falls back to :data:`DEFAULT_BUTTON_HOLD_THRESHOLD_S` when the
        button is not (yet) in the installation config. The timing
        detector in gateway_api.py uses this when no override is present.
        """
        btn = self.button_by_id(button_id)
        if btn is None:
            return DEFAULT_BUTTON_HOLD_THRESHOLD_S
        return btn.hold_threshold_s

    def to_dict(self) -> dict:
        """Serialize the full installation document for devices.json."""
        return {
            "modules": [mc.to_dict() for mc in self.modules],
            "buttons": [btn.to_dict() for btn in self.buttons],
        }
