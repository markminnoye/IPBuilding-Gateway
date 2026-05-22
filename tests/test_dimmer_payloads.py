"""Tests for gateway.payloads.dimmer."""

from gateway.models import DimmerCommand
from gateway.payloads.dimmer import (
    decode_dimmer_payload,
    decode_dimmer_status,
    encode_dim_command,
    encode_dim_off,
)


def test_decode_dimmer_status_reply_30():
    payload = b"I0154030"
    result = decode_dimmer_status(payload)
    assert result is not None
    assert result.internal_value_code == "030"
    assert result.level_percent == 30
    assert result.family_constant == "54"


def test_decode_dimmer_status_reply_99():
    result = decode_dimmer_status(b"I0154099")
    assert result.level_percent == 100


def test_decode_dimmer_status_off():
    result = decode_dimmer_status(b"I0154000")
    assert result.level_percent == 0


def test_encode_dim_command():
    wire = encode_dim_command(DimmerCommand(channel=0, level=30))
    assert wire == b"S0301030"
    parsed = decode_dimmer_payload(wire)
    assert parsed["action"] == "set"
    assert parsed["channel"] == 0


def test_encode_dim_off():
    assert encode_dim_off(1) == b"C1991030"
