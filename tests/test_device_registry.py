"""Tests for gateway.device_registry."""

from gateway.device_registry import (
    ButtonEvent,
    DeviceKey,
    DeviceRegistry,
    DimmerState,
    RelayState,
)
from gateway.types import DeviceType
from gateway.udp_bus import UDPPacket


def _make_pkt(src_ip: str, data: bytes) -> UDPPacket:
    return UDPPacket(
        data=data, src_ip=src_ip, src_port=1001, dst_ip="", dst_port=0, monotonic_ts=0.0
    )


def _registry_with_modules() -> DeviceRegistry:
    reg = DeviceRegistry()
    reg.register_module("10.10.1.30", DeviceType.RELAY)
    reg.register_module("10.10.1.40", DeviceType.DIMMER)
    reg.register_module("10.10.1.50", DeviceType.INPUT)
    return reg


class TestRelayState:
    def test_relay_status_on(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))

        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        state = reg.get_relay_state(key)
        assert state is not None
        assert state.state == "on"
        assert state.state_code == "0100"

    def test_relay_status_off(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000000"))

        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        state = reg.get_relay_state(key)
        assert state is not None
        assert state.state == "off"

    def test_relay_status_change_fires_callback(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))
        assert len(changes) == 1
        assert changes[0][1] == "unknown"
        assert changes[0][2] == "on"

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000000"))
        assert len(changes) == 2
        assert changes[1][1] == "on"
        assert changes[1][2] == "off"

    def test_relay_same_state_no_callback(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))
        assert len(changes) == 1

    def test_relay_multiple_channels(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))
        reg.handle_packet(_make_pkt("10.10.1.30", b"I000100100"))

        ch0 = reg.get_relay_state(DeviceKey(DeviceType.RELAY, "10.10.1.30", 0))
        ch10 = reg.get_relay_state(DeviceKey(DeviceType.RELAY, "10.10.1.30", 10))
        assert ch0 is not None and ch0.state == "on"
        assert ch10 is not None and ch10.state == "on"

    def test_pulse_reply_no_state_change(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.30", b"P000000000"))
        assert len(changes) == 0
        assert len(reg.all_relay_states()) == 0


class TestDimmerState:
    def test_dimmer_status_reply(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154030"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", -1)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 30
        assert state.internal_value_code == "030"

    def test_dimmer_off(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154000"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", -1)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 0

    def test_dimmer_change_fires_callback(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154030"))
        assert len(changes) == 1
        assert changes[0][1] is None
        assert changes[0][2] == 30

        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154099"))
        assert len(changes) == 2
        assert changes[1][1] == 30
        assert changes[1][2] == 100


class TestInputEvents:
    def test_button_press_event(self):
        reg = _registry_with_modules()
        events: list[tuple[DeviceKey, ButtonEvent]] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))

        # 13-byte button event: B + '-' + 6-byte id_core + 1-byte suffix + 0x03 + press(0x01) + 0x00 + E
        raw = b"B-\x41\x42\x43\x44\x45\x46\x47\x03\x01\x00E"
        reg.handle_packet(_make_pkt("10.10.1.50", raw))

        assert len(events) == 1
        assert events[0][1].action == "press"

    def test_button_release_event(self):
        reg = _registry_with_modules()
        events: list[tuple[DeviceKey, ButtonEvent]] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))

        raw = b"B-\x41\x42\x43\x44\x45\x46\x47\x03\x00\x00E"
        reg.handle_packet(_make_pkt("10.10.1.50", raw))

        assert len(events) == 1
        assert events[0][1].action == "release"

    def test_input_idle_no_event(self):
        """Idle keepalive replies should not fire button events."""
        reg = _registry_with_modules()
        events: list[tuple] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))

        # 14-byte idle reply: I + 0x02 + R + 3-byte status + 7x 0x00 + E
        raw = b"I\x02R\x00\x00\x00\x00\x00\x00\x00\x00\x00\x00E"
        reg.handle_packet(_make_pkt("10.10.1.50", raw))

        assert len(events) == 0


class TestUnknownModule:
    def test_unknown_ip_ignored(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.99", b"I00000100"))
        assert len(changes) == 0


class TestAllDevices:
    def test_all_devices_includes_relay_and_dimmer(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154030"))

        devices = reg.all_devices()
        assert len(devices) == 2
        types = {d["device_type"] for d in devices}
        assert types == {"relay", "dimmer"}


class TestCallbackError:
    def test_broken_callback_does_not_prevent_state_update(self):
        reg = _registry_with_modules()
        received: list[tuple] = []

        def bad(key, old, new):
            raise ValueError("boom")

        reg.on_state_changed(bad)
        reg.on_state_changed(lambda key, old, new: received.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000100"))

        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        assert reg.get_relay_state(key).state == "on"
        assert len(received) == 1
