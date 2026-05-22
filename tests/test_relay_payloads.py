"""Tests for gateway.payloads.relay."""

from gateway.models import RelayAction, RelayCommand
from gateway.payloads.relay import (
    decode_relay_payload,
    decode_relay_status,
    encode_relay_command,
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
