"""Tests for gateway.payloads.input."""

from gateway.payloads.input import decode_input_payload, encode_input_poll

IDLE_REPLY = bytes([0x49, 0x02, 0x52, 0x05, 0x02, 0x04, 0, 0, 0, 0, 0, 0, 0, 0x45])


def test_input_poll():
    parsed = decode_input_payload(encode_input_poll())
    assert parsed["family"] == "input_poll"


def test_input_idle_reply():
    parsed = decode_input_payload(IDLE_REPLY)
    assert parsed["family"] == "input_reply_binary"
    assert parsed["status_byte_0"] == 0x05
    assert parsed["length"] == 14


def test_input_button_event_press():
    raw = bytes.fromhex("422d2f8185190000df03010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_core_hex"] == "2f8185190000"


def test_input_button_event_release():
    raw = bytes.fromhex("422d1e6a85190000af03000045")
    parsed = decode_input_payload(raw)
    assert parsed["action"] == "release"


def test_input_button_event_marker_02():
    """Buttons with marker 0x02 (not only 0x03) — 2026-06-23 missing-buttons capture."""
    raw = bytes.fromhex("422de341851900001f02010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_core_hex"] == "e34185190000"
    assert parsed["id_suffix_hex"] == "1f"
    assert parsed["marker_hex"] == "02"


def test_input_button_event_rejects_bad_edge():
    assert decode_input_payload(bytes.fromhex("422de341851900001f02020045")) is None
