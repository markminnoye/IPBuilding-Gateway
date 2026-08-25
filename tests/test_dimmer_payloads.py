"""Tests for gateway.payloads.dimmer."""

import pytest

from gateway.models import DimmerCommand
from gateway.payloads.dimmer import (
    decode_dimmer_payload,
    decode_dimmer_status,
    encode_dim_command,
    encode_dim_off,
    encode_dim_start,
    encode_dim_stop,
    encode_dim_toggle,
    encode_dimmer_status_poll,
)


def test_decode_dimmer_status_reply_30():
    payload = b"I0154030"
    result = decode_dimmer_status(payload)
    assert result is not None
    assert result.internal_value_code == "030"
    assert result.channel == 0
    assert result.level_percent == 30
    assert result.family_constant == "54"


def test_decode_dimmer_status_reply_99():
    result = decode_dimmer_status(b"I0154099")
    assert result.channel == 0
    assert result.level_percent == 100


def test_decode_dimmer_status_off():
    result = decode_dimmer_status(b"I0154000")
    assert result.channel == 0
    assert result.level_percent == 0


def test_decode_dimmer_status_channel_in_code():
    """The leading digit of the 3-digit code is the channel (not a percent).

    Regression: I0154130 must decode to channel 1 / level 30, NOT level 130.
    Ground truth: 2026-05-14 REST↔UDP correlation for Bureau dimmer (ch1).
    """
    r30 = decode_dimmer_status(b"I0154130")
    assert r30.channel == 1
    assert r30.level_percent == 30
    assert r30.internal_value_code == "130"
    assert r30.family_constant == "54"
    assert decode_dimmer_payload(b"I0154130")["dialect_id"] == "dimmer.lab.status_reply"

    r70 = decode_dimmer_status(b"I0154170")
    assert r70.channel == 1
    assert r70.level_percent == 70

    r100 = decode_dimmer_status(b"I0154199")
    assert r100.channel == 1
    assert r100.level_percent == 100


def test_decode_dimmer_idle_heartbeat():
    """I0154999 is an idle/poll heartbeat, not a channel setpoint."""
    parsed = decode_dimmer_payload(b"I0154999")
    assert parsed is not None
    assert parsed["family"] == "dimmer_poll"
    assert parsed["action"] == "idle"
    # decode_dimmer_status only returns set-point replies
    assert decode_dimmer_status(b"I0154999") is None


def test_encode_dim_command():
    wire = encode_dim_command(DimmerCommand(channel=0, level=30))
    assert wire == b"S0301030"
    parsed = decode_dimmer_payload(wire)
    assert parsed["action"] == "set"
    assert parsed["channel"] == 0


def test_encode_dim_off():
    assert encode_dim_off(1) == b"C1991030"


def test_decode_dimmer_command_off_placeholder_is_zero():
    """C{ch}991030 is OFF; 99 is a placeholder, not 100%."""
    parsed = decode_dimmer_payload(b"C1991030")
    assert parsed is not None
    assert parsed["family"] == "dimmer_command"
    assert parsed["action"] == "off"
    assert parsed["channel"] == 1
    assert parsed["value_code"] == "99"
    assert parsed["level_percent"] == 0


def test_decode_nolf_dimmer_status_ch1_84():
    parsed = decode_dimmer_payload(b"I0115184")
    assert parsed is not None
    assert parsed["dialect_id"] == "dimmer.nolf.status_reply"
    assert parsed["family"] == "dimmer_status_reply"
    assert parsed["family_constant"] == "15"
    assert parsed["channel"] == 1
    assert parsed["level_percent"] == 84


def test_decode_nolf_dimmer_status_ch0_100():
    result = decode_dimmer_status(b"I0115099")
    assert result is not None
    assert result.family_constant == "15"
    assert result.channel == 0
    assert result.level_percent == 100


def test_decode_nolf_dimmer_status_ch3_off():
    result = decode_dimmer_status(b"I0115300")
    assert result is not None
    assert result.channel == 3
    assert result.level_percent == 0


def test_decode_nolf_dimmer_idle_keepalive():
    """I0115000 is family-15 idle sentinel, not ch0 off."""
    parsed = decode_dimmer_payload(b"I0115000")
    assert parsed is not None
    assert parsed["family"] == "dimmer_poll"
    assert parsed["action"] == "idle"
    assert parsed["dialect_id"] == "dimmer.nolf.idle_keepalive"
    assert "channel" not in parsed
    assert "level_percent" not in parsed
    assert decode_dimmer_status(b"I0115000") is None


def test_lab_dimmer_ch0_off_is_not_idle_sentinel():
    """I0154000 remains a valid lab ch0-off; 000 is not a global sentinel."""
    result = decode_dimmer_status(b"I0154000")
    assert result is not None
    assert result.channel == 0
    assert result.level_percent == 0
    assert result.family_constant == "54"


def test_encode_dimmer_status_poll_channel_zero():
    assert encode_dimmer_status_poll(0) == b"I0000000"


def test_encode_dimmer_status_poll_channel_two():
    assert encode_dimmer_status_poll(2) == b"I2000000"


def test_encode_dimmer_status_poll_invalid_channel():
    with pytest.raises(ValueError, match="0–7"):
        encode_dimmer_status_poll(8)
    with pytest.raises(ValueError, match="0–7"):
        encode_dimmer_status_poll(-1)


def test_decode_dimmer_status_poll_query():
    parsed = decode_dimmer_payload(b"I1000000")
    assert parsed is not None
    assert parsed["family"] == "dimmer_status_poll"
    assert parsed["channel"] == 1
    assert parsed["action"] == "status_query"


# --- Button / ramp dialect (downstream control) -----------------------------
# Wire-bytes match the 2026-06-22 p2p capture of IP1100PoE → IP0300PoE
# (`resources_and_docs/evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md`).

def test_encode_dim_toggle():
    """``T<ch>991000`` — short-press toggle; ``99`` value field is a placeholder."""
    assert encode_dim_toggle(0) == b"T0991000"
    assert encode_dim_toggle(1) == b"T1991000"
    assert encode_dim_toggle(7) == b"T7991000"


def test_encode_dim_start():
    """``D<ch>001003`` — hold start; module ramps and auto-reverses."""
    assert encode_dim_start(0) == b"D0001003"
    assert encode_dim_start(1) == b"D1001003"
    assert encode_dim_start(7) == b"D7001003"


def test_encode_dim_stop():
    """``D<ch>001000`` — hold stop; dimmer replies with ``I0154<ch><VV>``."""
    assert encode_dim_stop(0) == b"D0001000"
    assert encode_dim_stop(1) == b"D1001000"
    assert encode_dim_stop(7) == b"D7001000"
