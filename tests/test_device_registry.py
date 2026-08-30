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
        assert changes[0][1] is None
        assert changes[0][2].state == "on"

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000000"))
        assert len(changes) == 2
        assert changes[1][1].state == "on"
        assert changes[1][2].state == "off"

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


class TestNolfRelayCommandReply:
    def test_echo_updates_state_and_preserves_state_code(self):
        reg = _registry_with_modules()
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 6)
        reg.seed_relay_state(key, "on", "0115")

        changes: list[tuple] = []
        reg.on_state_changed(lambda k, old, new: changes.append((k, old, new)))
        reg.handle_packet(_make_pkt("10.10.1.30", b"C060000000"))

        state = reg.get_relay_state(key)
        assert state is not None
        assert state.state == "off"
        assert state.state_code == "0115"
        assert len(changes) == 1
        assert changes[0][2].state == "off"
        assert changes[0][2].state_code == "0115"

    def test_echo_logs_nolf_command_reply(self, caplog):
        import logging

        reg = _registry_with_modules()
        caplog.set_level(logging.INFO, logger="gateway.device_registry")
        reg.handle_packet(_make_pkt("10.10.1.30", b"C060000000"))
        assert any(
            "decoded relay.nolf.command_reply from 10.10.1.30: C060000000 (ch6 → off)"
            in r.message
            for r in caplog.records
        )

    def test_echo_first_packet_empty_state_code_no_warning(self, caplog):
        import logging

        reg = _registry_with_modules()
        caplog.set_level(logging.WARNING, logger="gateway.device_registry")
        reg.handle_packet(_make_pkt("10.10.1.30", b"C060000000"))

        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 6)
        state = reg.get_relay_state(key)
        assert state is not None
        assert state.state == "off"
        assert state.state_code == ""
        warnings = [
            r for r in caplog.records if "unrecognized state_code=" in r.message
        ]
        assert warnings == []

    def test_toggle_echo_does_not_change_state(self):
        reg = _registry_with_modules()
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 11)
        reg.seed_relay_state(key, "on", "0100")
        changes: list[tuple] = []
        reg.on_state_changed(lambda k, old, new: changes.append((k, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.30", b"T11001000"))

        state = reg.get_relay_state(key)
        assert state is not None
        assert state.state == "on"
        assert state.state_code == "0100"
        assert changes == []

    def test_p2p_toggle_from_dimmer_ip_does_not_update_relay(self):
        """Routing safety: T11001000 from a dimmer IP never hits the relay decoder."""
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda k, old, new: changes.append((k, old, new)))
        reg.handle_packet(_make_pkt("10.10.1.40", b"T11001000"))
        assert reg.get_relay_state(
            DeviceKey(DeviceType.RELAY, "10.10.1.30", 11)
        ) is None
        assert reg.get_relay_state(
            DeviceKey(DeviceType.RELAY, "10.10.1.40", 11)
        ) is None
        assert changes == []


class TestDimmerState:
    def test_dimmer_status_reply(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154030"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 30
        assert state.internal_value_code == "030"

    def test_dimmer_off(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154000"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 0

    def test_dimmer_channel_from_reply_code(self):
        """Reply I0154130 must land on channel 1 with level 30, not 130%.

        Regression for the channel-prefixed value code (Bureau dimmer ch1).
        """
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154130"))

        ch1 = reg.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1))
        assert ch1 is not None
        assert ch1.level_percent == 30
        assert ch1.internal_value_code == "130"
        # ch0 must remain untouched
        assert reg.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0)) is None

    def test_dimmer_idle_heartbeat_no_state_change(self):
        """The I0154999 idle heartbeat must not create or overwrite state."""
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        # Set a real level on ch1, then send idle heartbeats.
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154155"))  # ch1 -> 55%
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154999"))
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154999"))

        ch1 = reg.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1))
        assert ch1 is not None
        assert ch1.level_percent == 55  # unchanged by the heartbeats
        assert len(changes) == 1  # only the real setpoint fired

    def test_dimmer_change_fires_callback(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))

        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154030"))
        assert len(changes) == 1
        assert changes[0][1] is None
        assert changes[0][2].level_percent == 30

        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154099"))
        assert len(changes) == 2
        assert changes[1][1].level_percent == 30
        assert changes[1][2].level_percent == 100


class TestNolfDimmerCommandEcho:
    def test_set_echo_updates_level(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda k, old, new: changes.append((k, old, new)))
        reg.handle_packet(_make_pkt("10.10.1.40", b"S1231030"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 23
        assert len(changes) == 1
        assert changes[0][2].level_percent == 23

    def test_off_echo_is_zero_percent(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"C1991030"))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1)
        state = reg.get_dimmer_state(key)
        assert state is not None
        assert state.level_percent == 0

    def test_nolf_idle_keepalive_does_not_overwrite_level(self):
        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda k, old, new: changes.append((k, old, new)))
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115099"))  # ch0 → 100%
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115000"))
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115000"))

        ch0 = reg.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0))
        assert ch0 is not None
        assert ch0.level_percent == 100
        assert len(changes) == 1


class TestDimmerFamilyDetection:
    def test_unknown_until_the_module_answers(self):
        reg = _registry_with_modules()
        assert reg.get_dimmer_family("10.10.1.40") is None

    def test_lab_status_reply_marks_family_54(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0154130"))
        assert reg.get_dimmer_family("10.10.1.40") == "54"

    def test_nolf_status_reply_marks_family_15(self):
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115184"))
        assert reg.get_dimmer_family("10.10.1.40") == "15"

    def test_idle_keepalive_also_marks_the_family(self):
        """I0115000 carries no level but still identifies the generation."""
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115000"))
        assert reg.get_dimmer_family("10.10.1.40") == "15"

    def test_command_echo_marks_family_15(self):
        """Only Nolf-generation modules echo the command back."""
        reg = _registry_with_modules()
        reg.handle_packet(_make_pkt("10.10.1.40", b"S1231030"))
        assert reg.get_dimmer_family("10.10.1.40") == "15"

    def test_family_is_logged_once(self, caplog):
        import logging

        reg = _registry_with_modules()
        caplog.set_level(logging.INFO, logger="gateway.device_registry")
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115184"))
        reg.handle_packet(_make_pkt("10.10.1.40", b"I0115000"))

        lines = [r for r in caplog.records if "reply family" in r.message]
        assert len(lines) == 1


class TestInputEvents:
    def test_button_press_event(self):
        reg = _registry_with_modules()
        events: list[tuple[DeviceKey, ButtonEvent]] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))

        # 13-byte button event: B + '-' + 6-byte id_core + 1-byte suffix + marker + press + 0x00 + E
        raw = b"B-\x41\x42\x43\x44\x45\x46\x47\x02\x01\x00E"
        reg.handle_packet(_make_pkt("10.10.1.50", raw))

        assert len(events) == 1
        assert events[0][1].action == "press"
        assert events[0][1].id_hex == "41424347"
        assert events[0][1].dialect_id == "input.lab.button_event"

    def test_nolf_button_press_canonical_id(self):
        reg = _registry_with_modules()
        events: list[tuple[DeviceKey, ButtonEvent]] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))
        raw = bytes.fromhex("4201dac46c100000c301010045")
        reg.handle_packet(_make_pkt("10.10.1.50", raw))
        assert events[0][1].action == "press"
        assert events[0][1].id_hex == "dac46cc3"
        assert events[0][1].dialect_id == "input.nolf.button_event"

    def test_unknown_type_routes_and_warns_once(self, caplog):
        import logging
        reg = _registry_with_modules()
        events: list[tuple[DeviceKey, ButtonEvent]] = []
        reg.on_button_event(lambda key, evt: events.append((key, evt)))
        caplog.set_level(logging.WARNING, logger="gateway.device_registry")
        raw = bytes.fromhex("42aa2f8185190000df03010045")
        reg.handle_packet(_make_pkt("10.10.1.50", raw))
        reg.handle_packet(_make_pkt("10.10.1.50", raw))
        assert len(events) == 2
        assert events[0][1].dialect_id == "input.unknown.button_event"
        warnings = [r for r in caplog.records if "Unknown input type byte" in r.message]
        assert len(warnings) == 1

    def test_undecoded_warns_once_per_signature(self, caplog):
        import logging
        reg = _registry_with_modules()
        caplog.set_level(logging.WARNING, logger="gateway.device_registry")
        junk = b"F\x28xxxxE"
        reg.handle_packet(_make_pkt("10.10.1.50", junk))
        reg.handle_packet(_make_pkt("10.10.1.50", junk))
        warnings = [r for r in caplog.records if "undecoded RX" in r.message]
        assert len(warnings) == 1

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


class TestSeedState:
    """seed_relay_state / seed_dimmer_state populate the cache directly
    without firing any state-changed callback. Used by the UDP relay
    status poll at startup."""

    def test_seed_relay_state_sets_value(self):
        reg = _registry_with_modules()
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 4)
        reg.seed_relay_state(key, "on", "0100")

        rs = reg.get_relay_state(key)
        assert rs is not None
        assert rs.state == "on"
        assert rs.state_code == "0100"

    def test_seed_relay_state_does_not_fire_callback(self):
        reg = _registry_with_modules()
        received: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: received.append((key, old, new)))

        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 5)
        reg.seed_relay_state(key, "on")

        assert reg.get_relay_state(key).state == "on"
        assert received == []  # no callback fired on bootstrap

    def test_seed_dimmer_state_sets_value(self):
        reg = _registry_with_modules()
        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 2)
        reg.seed_dimmer_state(key, 75, "175")

        ds = reg.get_dimmer_state(key)
        assert ds is not None
        assert ds.level_percent == 75
        assert ds.internal_value_code == "175"

    def test_seed_dimmer_state_clamps_and_rejects_none(self):
        reg = _registry_with_modules()
        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 3)

        # Above 100 -> clamped to 100
        reg.seed_dimmer_state(key, 250)
        assert reg.get_dimmer_state(key).level_percent == 100

        # Below 0 -> clamped to 0
        reg.seed_dimmer_state(key, -10)
        assert reg.get_dimmer_state(key).level_percent == 0

        # None rejected
        import pytest
        with pytest.raises(ValueError):
            reg.seed_dimmer_state(key, None)  # type: ignore[arg-type]

    def test_seed_dimmer_state_does_not_fire_callback(self):
        reg = _registry_with_modules()
        received: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: received.append((key, old, new)))

        key = DeviceKey(DeviceType.DIMMER, "10.10.1.40", 1)
        reg.seed_dimmer_state(key, 50)

        assert reg.get_dimmer_state(key).level_percent == 50
        assert received == []


class TestUnrecognizedRelayStateCode:
    def test_first_seen_0015_is_off_no_warn(self, caplog):
        import logging

        reg = _registry_with_modules()
        caplog.set_level(logging.WARNING, logger="gateway.device_registry")
        pkt = _make_pkt("10.10.1.30", b"I00000015")
        reg.handle_packet(pkt)
        reg.handle_packet(pkt)

        warnings = [
            r for r in caplog.records if "unrecognized state_code=" in r.message
        ]
        assert warnings == []
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        rs = reg.get_relay_state(key)
        assert rs is not None
        assert rs.state == "off"
        assert rs.state_code == "0015"

    def test_first_seen_0200_warns_once(self, caplog):
        import logging

        reg = _registry_with_modules()
        caplog.set_level(logging.WARNING, logger="gateway.device_registry")
        pkt = _make_pkt("10.10.1.30", b"I00000200")
        reg.handle_packet(pkt)
        reg.handle_packet(pkt)

        warnings = [
            r for r in caplog.records if "unrecognized state_code=0200" in r.message
        ]
        assert len(warnings) == 1
        key = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        rs = reg.get_relay_state(key)
        assert rs is not None
        assert rs.state == "unknown"
        assert rs.state_code == "0200"

    def test_0015_to_0115_fires_callback(self, caplog):
        import logging

        reg = _registry_with_modules()
        changes: list[tuple] = []
        reg.on_state_changed(lambda key, old, new: changes.append((key, old, new)))
        caplog.set_level(logging.INFO, logger="gateway.device_registry")

        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000015"))
        reg.handle_packet(_make_pkt("10.10.1.30", b"I00000115"))

        assert len(changes) == 2
        assert changes[0][2].state == "off"
        assert changes[0][2].state_code == "0015"
        assert changes[1][1].state_code == "0015"
        assert changes[1][2].state_code == "0115"
        assert changes[1][2].state == "on"
        assert any("0015" in r.message and "0115" in r.message for r in caplog.records)
