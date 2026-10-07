"""In-memory device state registry for field bus modules."""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from typing import Any, Callable

from gateway.payloads.dimmer import decode_dimmer_payload
from gateway.payloads.input import decode_input_payload
from gateway.payloads.relay import decode_relay_payload
from gateway.types import DeviceKey, DeviceType
from gateway.udp_bus import UDPPacket, format_payload

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
    type_hex: str = ""
    dialect_id: str = ""


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
    _dimmer_last_channel: dict[str, int] = field(default_factory=dict)  # ip → last commanded channel
    _dimmer_families: dict[str, str] = field(default_factory=dict)  # ip → reply family constant
    _state_callbacks: list[StateChangeCallback] = field(default_factory=list)
    _event_callbacks: list[EventCallback] = field(default_factory=list)
    _module_ip_type: dict[str, DeviceType] = field(default_factory=dict)
    _seen_unrecognized_state_codes: set[tuple[str, int, str]] = field(
        default_factory=set
    )
    _seen_unknown_input_types: set[str] = field(default_factory=set)
    _seen_undecoded_signatures: set[tuple[str, int, int | None, int | None]] = field(
        default_factory=set
    )

    def register_module(self, module_ip: str, device_type: DeviceType) -> None:
        """Associate a module IP with a device type for packet routing."""
        self._module_ip_type[module_ip] = device_type

    def on_state_changed(self, cb: StateChangeCallback) -> StateChangeCallback:
        self._state_callbacks.append(cb)
        return cb

    def unregister_state_changed(self, cb: StateChangeCallback) -> None:
        self._state_callbacks = [c for c in self._state_callbacks if c is not cb]

    def on_button_event(self, cb: EventCallback) -> EventCallback:
        self._event_callbacks.append(cb)
        return cb

    def unregister_button_event(self, cb: EventCallback) -> None:
        self._event_callbacks = [c for c in self._event_callbacks if c is not cb]

    # -- public query API --

    def get_relay_state(self, key: DeviceKey) -> RelayState | None:
        return self._relay_states.get(key)

    def get_dimmer_state(self, key: DeviceKey) -> DimmerState | None:
        return self._dimmer_states.get(key)

    def seed_relay_state(
        self, key: DeviceKey, state: str, state_code: str = ""
    ) -> None:
        """Set relay state without firing state-changed callbacks.

        Used by the UDP relay status poll at startup to populate the
        in-memory cache from per-channel ``I<CH>00`` reads. Unlike
        ``handle_packet`` this never broadcasts; subscribers are wired in
        later when the gateway API is created.
        """
        self._relay_states[key] = RelayState(state=state, state_code=state_code)
        self._warn_if_unknown_relay_state(
            key.module_ip, key.channel, state, state_code
        )

    def seed_dimmer_state(
        self,
        key: DeviceKey,
        level_percent: int,
        internal_value_code: str = "",
    ) -> None:
        """Set dimmer state without firing state-changed callbacks.

        Used by the UDP dimmer status poll at startup
        (``I{ch}000000`` → ``I0154{ch}{vv}``, RE 2026-08-05). Unlike
        ``handle_packet`` this never broadcasts; subscribers are wired in
        later when the gateway API is created.
        """
        if level_percent is None:
            raise ValueError("level_percent must not be None")
        clamped = max(0, min(int(level_percent), 100))
        self._dimmer_states[key] = DimmerState(
            level_percent=clamped,
            internal_value_code=internal_value_code,
        )

    def track_dimmer_channel(self, module_ip: str, channel: int) -> None:
        """Remember the last commanded channel for a dimmer module.

        Status replies normally encode the channel as the leading digit of
        the value code (decoded in :func:`decode_dimmer_payload`), so this is
        only a fallback for replies where the channel cannot be resolved.
        """
        self._dimmer_last_channel[module_ip] = channel

    def get_dimmer_family(self, module_ip: str) -> str | None:
        """Return the reply family constant last seen from a dimmer module.

        ``"54"`` for lab IP0300PoE, ``"15"`` for Nolf-generation hardware,
        ``None`` until the module has answered. Command encodings that differ
        per generation (notably OFF) resolve against this.
        """
        return self._dimmer_families.get(module_ip)

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

    def _warn_if_unknown_relay_state(
        self, module_ip: str, channel: int, state: str, state_code: str
    ) -> None:
        if state != "unknown" or not state_code:
            return
        key = (module_ip, channel, state_code)
        if key in self._seen_unrecognized_state_codes:
            return
        self._seen_unrecognized_state_codes.add(key)
        log.warning(
            "Relay %s ch%d: unrecognized state_code=%s",
            module_ip,
            channel,
            state_code,
        )

    def _log_undecoded(self, module_ip: str, data: bytes) -> None:
        first = data[0] if data else None
        last = data[-1] if data else None
        key = (module_ip, len(data), first, last)
        if key in self._seen_undecoded_signatures:
            return
        self._seen_undecoded_signatures.add(key)
        log.warning("undecoded RX from %s: %s", module_ip, format_payload(data))

    def _handle_relay(self, module_ip: str, data: bytes) -> None:
        parsed = decode_relay_payload(data)
        if not parsed:
            self._log_undecoded(module_ip, data)
            return
        family = parsed.get("family")
        if family == "relay_status":
            ch = parsed["channel"]
            key = DeviceKey(DeviceType.RELAY, module_ip, ch)
            new_state = parsed["state"]
            new_code = parsed["state_code"]
            old = self._relay_states.get(key)
            new_rs = RelayState(state=new_state, state_code=new_code)
            self._relay_states[key] = new_rs
            self._warn_if_unknown_relay_state(module_ip, ch, new_state, new_code)
            if (
                old is None
                or old.state != new_state
                or old.state_code != new_code
            ):
                log.info(
                    "Relay %s ch%d: %s (%s) -> %s (%s)",
                    module_ip,
                    ch,
                    old.state if old else "unknown",
                    old.state_code if old else "",
                    new_state,
                    new_code,
                )
                self._fire_state_changed(key, old, new_rs)
        elif family == "relay_command_reply":
            ch = parsed["channel"]
            new_state = parsed["state"]
            raw = parsed.get("raw", "")
            log.info(
                "decoded relay.nolf.command_reply from %s: %s (ch%d → %s)",
                module_ip,
                raw,
                ch,
                new_state,
            )
            if new_state == "unknown":
                return
            key = DeviceKey(DeviceType.RELAY, module_ip, ch)
            old = self._relay_states.get(key)
            # Echo carries no reliable quartet; keep the last polled code.
            # First-ever echo keeps "" — _warn_if_unknown_relay_state already
            # skips that case via `not state_code`.
            preserved_code = old.state_code if old else ""
            new_rs = RelayState(state=new_state, state_code=preserved_code)
            self._relay_states[key] = new_rs
            if old is None or old.state != new_state:
                self._fire_state_changed(key, old, new_rs)
        elif family == "relay_reply_candidate":
            pass  # pulse echo, no state change

    def _note_dimmer_family(self, module_ip: str, parsed: dict[str, Any]) -> None:
        """Learn which dimmer generation a module belongs to from its reply.

        Status and idle frames carry the family constant directly. A module
        that echoes the command back instead of answering ``I0154…`` is
        Nolf-generation by construction, so the echo counts as family ``15``.
        """
        observed = parsed.get("family_constant")
        if observed is None and parsed.get("family") == "dimmer_command":
            observed = "15"
        if observed is None or self._dimmer_families.get(module_ip) == observed:
            return
        self._dimmer_families[module_ip] = observed
        log.info("Dimmer %s speaks reply family %s", module_ip, observed)

    def _handle_dimmer(self, module_ip: str, data: bytes) -> None:
        parsed = decode_dimmer_payload(data)
        if not parsed:
            self._log_undecoded(module_ip, data)
            return
        family = parsed.get("family")
        self._note_dimmer_family(module_ip, parsed)
        if family == "dimmer_status_reply":
            # The reply encodes the channel as the leading digit of the value
            # code (e.g. I0154130 → channel 1).  Fall back to the last
            # commanded channel only if the decoder could not resolve it.
            ch = parsed.get("channel")
            if ch is None:
                ch = self._dimmer_last_channel.get(module_ip, 0)
            key = DeviceKey(DeviceType.DIMMER, module_ip, ch)
            new_level = parsed.get("level_percent")
            new_code = parsed.get("internal_value_code", "")
            old = self._dimmer_states.get(key)
            new_ds = DimmerState(
                level_percent=new_level, internal_value_code=new_code
            )
            self._dimmer_states[key] = new_ds
            if old is None or old.level_percent != new_level:
                log.info(
                    "Dimmer %s ch%d: %s -> %s%%",
                    module_ip,
                    ch,
                    old.level_percent if old else None,
                    new_level,
                )
                self._fire_state_changed(key, old, new_ds)
        elif family == "dimmer_command":
            # Nolf dimmers echo the command instead of I0115…; the echo is
            # the state source (lab dimmers reply I0154… and never hit this).
            ch = parsed.get("channel")
            new_level = parsed.get("level_percent")
            if ch is None or new_level is None:
                return
            raw = parsed.get("raw", "")
            log.info(
                "decoded dimmer.nolf.command_echo from %s: %s (ch%d → %s%%)",
                module_ip,
                raw,
                ch,
                new_level,
            )
            key = DeviceKey(DeviceType.DIMMER, module_ip, ch)
            new_code = parsed.get("internal_value_code") or parsed.get(
                "value_code", ""
            )
            old = self._dimmer_states.get(key)
            new_ds = DimmerState(
                level_percent=new_level, internal_value_code=new_code
            )
            self._dimmer_states[key] = new_ds
            if old is None or old.level_percent != new_level:
                self._fire_state_changed(key, old, new_ds)

    def _handle_input(self, module_ip: str, data: bytes) -> None:
        parsed = decode_input_payload(data)
        if not parsed:
            self._log_undecoded(module_ip, data)
            return
        family = parsed.get("family")
        if family == "input_button_event":
            action = parsed.get("action", "unknown")
            id_hex = parsed.get("id_hex") or ""
            type_hex = parsed.get("type_hex") or ""
            dialect_id = parsed.get("dialect_id") or ""
            if dialect_id == "input.unknown.button_event" and type_hex not in self._seen_unknown_input_types:
                self._seen_unknown_input_types.add(type_hex)
                log.warning(
                    "Unknown input type byte 0x%s from %s: id=%s wire=%s action=%s",
                    type_hex,
                    module_ip,
                    id_hex,
                    parsed.get("id_wire_hex"),
                    action,
                )
            evt = ButtonEvent(
                action=action,
                id_hex=id_hex,
                type_hex=type_hex,
                dialect_id=dialect_id,
            )
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
