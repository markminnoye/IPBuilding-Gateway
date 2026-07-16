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


def northbound_module_id(mac: str, ip: str) -> str:
    """Stable module identifier for API/UI grouping.

    Prefer normalised MAC when known; fall back to IP while discovery has not
    yet populated hardware addresses (e.g. IPA-imported configs).
    """
    return mac if mac else ip


def module_by_northbound_id(
    installation: "InstallationConfig", module_id: str,
) -> "ModuleConfig | None":
    """Resolve a module from API ``module_id`` (MAC or IP fallback)."""
    key = module_id.lower()
    mc = installation.module_by_mac(key)
    if mc is not None:
        return mc
    return installation.module_by_ip(module_id)


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

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json; entity_id is always derived."""
        # The ``id`` (entity_id) is derived on-the-fly via ``make_entity_id`` —
        # never stored, never round-tripped. See module-level docstring.
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
class PushbuttonConfig:
    """A single physical pushbutton on an IP1100PoE input module.

    Pushbuttons are not channels — they have no entity_id of the form
    `{module_ip}-{ch}`. They are event sources on a module. The gateway
    uses :attr:`hold_threshold_s` to classify press→release timing into
    ``press`` vs ``long_press`` events; the value is normally seeded from
    ``getButtons.func2.holdSeconds`` on the input module (operator-bevestigd
    2026-06-16: dit is dezelfde drempel die IPBox hanteert).
    """

    id: str  # hardware hex, e.g. "2f8185190000df" (14 lowercase hex chars)
    module_id: str = ""  # parent module MAC — derived from nesting position, never read from the button's own dict
    channel: int | None = None  # physical port index; from getButtons/backupConfig "index"
    name: str = ""  # operator-friendly description, default from getButtons.descr
    room: str = ""  # from getButtons.gr
    active: bool = True
    hold_threshold_s: float = DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def to_dict(self) -> dict:
        """Serialize to dict for devices.json. module_id is implied by nesting, so it is excluded."""
        d: dict = {
            "id": self.id,
            "name": self.name,
            "room": self.room,
            "active": self.active,
            "hold_threshold_s": self.hold_threshold_s,
        }
        if self.channel is not None:
            d["channel"] = self.channel
        return d

    @classmethod
    def from_dict(cls, data: dict, module_id: str = "") -> "PushbuttonConfig":
        # Legacy multi_press / multi_press_window_ms keys in devices.json are
        # ignored — multi-press is a global GatewayConfig / add-on option.
        return cls(
            id=data["id"],
            module_id=module_id,
            channel=data.get("channel"),
            name=data.get("name", ""),
            room=data.get("room", ""),
            active=data.get("active", True),
            hold_threshold_s=float(
                data.get("hold_threshold_s", DEFAULT_BUTTON_HOLD_THRESHOLD_S)
            ),
        )


@dataclass
class DetectorConfig:
    """A single physical detector on an IP1100PoE input module.

    Schema placeholder only — no runtime behaviour, no UDP protocol
    decoding, not exposed via the REST API. There is no confirmed
    ``getDetectors`` sample to base a richer schema on yet; this exists
    purely so a devices.json ``detectors[]`` array round-trips without
    data loss.
    """

    id: str
    name: str = ""
    room: str = ""
    active: bool = True

    def to_dict(self) -> dict:
        return {"id": self.id, "name": self.name, "room": self.room, "active": self.active}

    @classmethod
    def from_dict(cls, data: dict) -> "DetectorConfig":
        return cls(
            id=data["id"],
            name=data.get("name", ""),
            room=data.get("room", ""),
            active=data.get("active", True),
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
    pushbuttons: list[PushbuttonConfig] = field(default_factory=list)
    detectors: list[DetectorConfig] = field(default_factory=list)
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
        """Serialize to dict for devices.json, excluding runtime-only fields.

        Type-conditional: an input module's entry shows pushbuttons/detectors
        (never channels); a relay/dimmer module's entry shows channels
        (never pushbuttons/detectors). A module entry only ever carries the
        fields relevant to its own type.
        """
        d: dict = {
            "name": self.name,
            "ip": self.ip,
            "type": self.type.value,
            "firmware": self.firmware,
            "model": self.model,
            "mac": self.mac,
        }
        if self.type == DeviceType.INPUT:
            d["pushbuttons"] = [b.to_dict() for b in self.pushbuttons]
            d["detectors"] = [x.to_dict() for x in self.detectors]
        else:
            d["channels"] = [c.to_dict() for c in self.channels]
        return d

    @classmethod
    def from_dict(cls, data: dict) -> "ModuleConfig":
        """Reconstruct from a devices.json dict entry, skipping runtime fields."""
        mac = data.get("mac", "")
        mc = cls(
            name=data.get("name", data.get("ip", "")),
            ip=data["ip"],
            type=DeviceType(data["type"]),
            firmware=data.get("firmware", ""),
            model=data.get("model", ""),
            mac=mac,
            channels=[ChannelConfig.from_dict(c) for c in data.get("channels", [])],
        )
        mc.pushbuttons = [
            PushbuttonConfig.from_dict(b, module_id=mac) for b in data.get("pushbuttons", [])
        ]
        mc.detectors = [DetectorConfig.from_dict(x) for x in data.get("detectors", [])]
        return mc


@dataclass
class InstallationConfig:
    """Loaded and validated installation configuration."""

    modules: list[ModuleConfig] = field(default_factory=list)
    # Physical pushbuttons (IP1100PoE). Authoritative for hold_threshold_s and
    # event routing. Persisted nested under each input module's
    # "pushbuttons" key (see ModuleConfig.to_dict()).
    pushbuttons: list[PushbuttonConfig] = field(default_factory=list)

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
    # pushbutton hardware id (lowercase) -> PushbuttonConfig
    _pushbuttons_by_id: dict[str, PushbuttonConfig] = field(default_factory=dict)

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
        if "buttons" in raw:
            raise InstallationError(
                "Old flat devices.json format detected (top-level 'buttons' key). "
                "Run scripts/migrate_buttons_to_nested.py to convert it to "
                "modules[].pushbuttons[] before loading."
            )

        seen_ipbox_ids: set[int] = set()
        seen_device_ids: set[str] = set()
        modules: list[ModuleConfig] = []
        pushbuttons: list[PushbuttonConfig] = []
        ipbox_id_to_entry: dict[int, tuple[DeviceType, str, int]] = {}
        device_id_to_entry: dict[str, tuple[DeviceType, str, int]] = {}
        entry_to_device_id: dict[tuple[DeviceType, str, int], str] = {}
        modules_by_ip: dict[str, ModuleConfig] = {}
        modules_by_mac: dict[str, ModuleConfig] = {}
        pushbuttons_by_id: dict[str, PushbuttonConfig] = {}

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
                        semantic_type=(
                            "light"
                            if dtype == DeviceType.DIMMER
                            else ch_entry.get("semantic_type", "light")
                        ),
                        active=ch_entry.get("active", True),
                        max_watt=ch_entry.get("max_watt", 0),
                    )
                )

            pushbuttons_for_module: list[PushbuttonConfig] = []
            for btn_entry in mod.get("pushbuttons", []):
                btn_id = btn_entry.get("id")
                if not btn_id:
                    log.warning("Skipping pushbutton entry without id: %r", btn_entry)
                    continue
                key = btn_id.lower()
                if key in pushbuttons_by_id:
                    raise InstallationError(f"Duplicate pushbutton id {btn_id!r}")
                btn = PushbuttonConfig.from_dict(btn_entry, module_id=mac_normalised)
                pushbuttons_for_module.append(btn)
                pushbuttons_by_id[key] = btn
                pushbuttons.append(btn)

            detectors = [DetectorConfig.from_dict(d) for d in mod.get("detectors", [])]

            mc = ModuleConfig(
                name=mod.get("name", mod_ip),
                ip=mod_ip,
                type=dtype,
                firmware=firmware,
                model=mod.get("model", ""),
                mac=mac_normalised,
                channels=channels,
                pushbuttons=pushbuttons_for_module,
                detectors=detectors,
            )
            modules.append(mc)
            modules_by_ip[mod_ip] = mc
            if mac_normalised:
                modules_by_mac[mac_normalised] = mc

        inst = cls(modules=modules, pushbuttons=pushbuttons)
        inst._ipbox_id_to_entry = ipbox_id_to_entry
        inst._modules_by_ip = modules_by_ip
        inst._modules_by_mac = modules_by_mac
        inst._device_id_to_entry = device_id_to_entry
        inst._entry_to_device_id = entry_to_device_id
        inst._pushbuttons_by_id = pushbuttons_by_id
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

    def pushbutton_by_id(self, button_id: str) -> PushbuttonConfig | None:
        """Look up a pushbutton by hardware id (case-insensitive). Returns None if unknown."""
        if not button_id:
            return None
        return self._pushbuttons_by_id.get(button_id.lower())

    def pushbutton_threshold(self, button_id: str) -> float:
        """Return the hold threshold (seconds) for a pushbutton.

        Falls back to :data:`DEFAULT_BUTTON_HOLD_THRESHOLD_S` when the
        pushbutton is not (yet) in the installation config. The timing
        detector in gateway_api.py uses this when no override is present.
        """
        btn = self.pushbutton_by_id(button_id)
        if btn is None:
            return DEFAULT_BUTTON_HOLD_THRESHOLD_S
        return btn.hold_threshold_s
