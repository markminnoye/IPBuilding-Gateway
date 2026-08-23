"""Tests for gateway.payloads.relay."""

from gateway.models import RelayAction, RelayCommand
from gateway.payloads.relay import (
    decode_relay_payload,
    decode_relay_status,
    encode_relay_command,
    relay_state_from_code,
    strip_j_envelope,
)


def test_decode_relay_status_reply_on():
    payload = b"I00100100"  # channel 0010 (10), state 0100 (ON)
    result = decode_relay_status(payload)
    assert result is not None
    assert result.channel == 10
    assert result.state == "on"


def test_decode_relay_status_reply_off():
    payload = b"I00000000"  # channel 0000, state 0000 (OFF)
    result = decode_relay_status(payload)
    assert result is not None
    assert result.channel == 0
    assert result.state == "off"


def test_strip_j_envelope():
    assert strip_j_envelope(b"mJS0000") == b"S0000"
    assert strip_j_envelope(b"}JC0000") == b"C0000"


def test_encode_relay_on_wire():
    """Hub→relay is raw ASCII on UDP/1001 (RE 2026-05-19; no mJ envelope)."""
    wire = encode_relay_command(RelayCommand(channel=0, action=RelayAction.ON))
    assert wire == b"S0000"
    parsed = decode_relay_payload(wire)
    assert parsed["action"] == "on"
    assert parsed["channel"] == 0


def test_pulse_reply_candidate():
    parsed = decode_relay_payload(b"P000000000")
    assert parsed["family"] == "relay_reply_candidate"


def test_relay_state_from_code_prefix_rule():
    assert relay_state_from_code("0100") == "on"
    assert relay_state_from_code("0000") == "off"
    assert relay_state_from_code("0015") == "off"
    assert relay_state_from_code("0115") == "on"
    assert relay_state_from_code("0200") == "unknown"
    assert relay_state_from_code("9999") == "unknown"
    assert relay_state_from_code("abc") == "unknown"


def test_decode_relay_status_nolf_0015_off():
    result = decode_relay_status(b"I00000015")
    assert result is not None
    assert result.channel == 0
    assert result.state == "off"
    assert result.state_code == "0015"


def test_decode_relay_status_nolf_0115_on():
    result = decode_relay_status(b"I00000115")
    assert result is not None
    assert result.channel == 0
    assert result.state == "on"
    assert result.state_code == "0115"


def test_decode_relay_status_true_unknown():
    result = decode_relay_status(b"I00000200")
    assert result is not None
    assert result.state == "unknown"
    assert result.state_code == "0200"
