"""In-memory device state registry for field bus modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from gateway.payloads.dimmer import decode_dimmer_payload
from gateway.payloads.input import decode_input_payload
from gateway.payloads.relay import decode_relay_payload
from gateway.types import DeviceKey, DeviceType
from gateway.udp_bus import UDPPacket

log = logging.getLogger(__name__)


@dataclass
class RelayState:
    state: str = "unknown"  # "on" / "off" / "unknown"
    state_code: str = ""


@dataclass
class DimmerState:
    level_percent: int | None = None
    internal_value_code: str = ""


@dataclass
class ButtonEvent:
    action: str  # "press" / "release"
    id_hex: str


StateChangeCallback = Callable[[DeviceKey, Any, Any], None]
EventCallback = Callable[[DeviceKey, ButtonEvent], None]


@dataclass
class DeviceRegistry:
    """Tracks device state from parsed field bus replies.

    State is updated by calling ``handle_packet`` with raw UDP packets.
    Register callbacks via ``on_state_changed`` (relay/dimmer state diffs)
    and ``on_button_event`` (input press/release, no persistent state).
    """

    _relay_states: dict[DeviceKey, RelayState] = field(default_factory=dict)
    _dimmer_states: dict[DeviceKey, DimmerState] = field(default_factory=dict)
    _state_callbacks: list[StateChangeCallback] = field(default_factory=list)
    _event_callbacks: list[EventCallback] = field(default_factory=list)
    _module_ip_type: dict[str, DeviceType] = field(default_factory=dict)

    def register_module(self, module_ip: str, device_type: DeviceType) -> None:
        """Associate a module IP with a device type for packet routing."""
        self._module_ip_type[module_ip] = device_type

    def on_state_changed(self, cb: StateChangeCallback) -> None:
        self._state_callbacks.append(cb)

    def on_button_event(self, cb: EventCallback) -> None:
        self._event_callbacks.append(cb)

    # -- public query API --

    def get_relay_state(self, key: DeviceKey) -> RelayState | None:
        return self._relay_states.get(key)

    def get_dimmer_state(self, key: DeviceKey) -> DimmerState | None:
        return self._dimmer_states.get(key)

    def all_relay_states(self) -> dict[DeviceKey, RelayState]:
        return dict(self._relay_states)

    def all_dimmer_states(self) -> dict[DeviceKey, DimmerState]:
        return dict(self._dimmer_states)

    def all_devices(self) -> list[dict[str, Any]]:
        """Return a flat list of all known devices with current state."""
        devices: list[dict[str, Any]] = []
        for key, rs in self._relay_states.items():
            devices.append({
                "device_type": key.device_type.value,
                "module_ip": key.module_ip,
                "channel": key.channel,
                "state": rs.state,
                "state_code": rs.state_code,
            })
        for key, ds in self._dimmer_states.items():
            devices.append({
                "device_type": key.device_type.value,
                "module_ip": key.module_ip,
                "channel": key.channel,
                "level_percent": ds.level_percent,
                "internal_value_code": ds.internal_value_code,
            })
        return devices

    # -- packet handling --

    def handle_packet(self, pkt: UDPPacket) -> None:
        """Parse a raw UDP packet and update state if applicable."""
        src = pkt.src_ip
        dtype = self._module_ip_type.get(src)
        if dtype is None:
            return

        if dtype == DeviceType.RELAY:
            self._handle_relay(src, pkt.data)
        elif dtype == DeviceType.DIMMER:
            self._handle_dimmer(src, pkt.data)
        elif dtype == DeviceType.INPUT:
            self._handle_input(src, pkt.data)

    def _handle_relay(self, module_ip: str, data: bytes) -> None:
        parsed = decode_relay_payload(data)
        if not parsed:
            return
        family = parsed.get("family")
        if family == "relay_status":
            ch = parsed["channel"]
            key = DeviceKey(DeviceType.RELAY, module_ip, ch)
            new_state = parsed["state"]
            new_code = parsed["state_code"]
            old = self._relay_states.get(key)
            old_state = old.state if old else "unknown"
            self._relay_states[key] = RelayState(state=new_state, state_code=new_code)
            if old_state != new_state:
                log.info("Relay %s ch%d: %s -> %s", module_ip, ch, old_state, new_state)
                self._fire_state_changed(key, old_state, new_state)
        elif family == "relay_reply_candidate":
            pass  # pulse echo, no state change

    def _handle_dimmer(self, module_ip: str, data: bytes) -> None:
        parsed = decode_dimmer_payload(data)
        if not parsed:
            return
        family = parsed.get("family")
        if family == "dimmer_status_reply":
            ch = parsed.get("channel", -1)
            key = DeviceKey(DeviceType.DIMMER, module_ip, ch)
            new_level = parsed.get("level_percent")
            new_code = parsed.get("internal_value_code", "")
            old = self._dimmer_states.get(key)
            old_level = old.level_percent if old else None
            self._dimmer_states[key] = DimmerState(
                level_percent=new_level, internal_value_code=new_code
            )
            if old_level != new_level:
                log.info("Dimmer %s ch%d: %s -> %s%%", module_ip, ch, old_level, new_level)
                self._fire_state_changed(key, old_level, new_level)

    def _handle_input(self, module_ip: str, data: bytes) -> None:
        parsed = decode_input_payload(data)
        if not parsed:
            return
        family = parsed.get("family")
        if family == "input_button_event":
            action = parsed.get("action", "unknown")
            id_hex = f"{parsed.get('id_core_hex', '')}{parsed.get('id_suffix_hex', '')}"
            evt = ButtonEvent(action=action, id_hex=id_hex)
            key = DeviceKey(DeviceType.INPUT, module_ip, 0)
            log.info("Input %s button %s: %s", module_ip, id_hex, action)
            self._fire_button_event(key, evt)

    # -- callback dispatch --

    def _fire_state_changed(self, key: DeviceKey, old: Any, new: Any) -> None:
        for cb in self._state_callbacks:
            try:
                cb(key, old, new)
            except Exception:
                log.exception("State change callback error")

    def _fire_button_event(self, key: DeviceKey, evt: ButtonEvent) -> None:
        for cb in self._event_callbacks:
            try:
                cb(key, evt)
            except Exception:
                log.exception("Button event callback error")
