"""Tests for gateway.payloads.input."""

from gateway.payloads.input import decode_input_payload, encode_input_poll

IDLE_REPLY_LAB = bytes([0x49, 0x02, 0x52, 0x05, 0x02, 0x04, 0, 0, 0, 0, 0, 0, 0, 0x45])
IDLE_REPLY_NOLF = bytes.fromhex("49022800000000000000000045")


def test_input_poll():
    parsed = decode_input_payload(encode_input_poll())
    assert parsed["family"] == "input_poll"


def test_input_idle_reply_lab():
    parsed = decode_input_payload(IDLE_REPLY_LAB)
    assert parsed["family"] == "input_reply_binary"
    assert parsed["status_byte_0"] == 0x05
    assert parsed["length"] == 14
    assert parsed["family_hex"] == "52"
    assert parsed["dialect_id"] == "input.lab.idle_reply"


def test_input_idle_reply_nolf():
    parsed = decode_input_payload(IDLE_REPLY_NOLF)
    assert parsed["family"] == "input_reply_binary"
    assert parsed["length"] == 13
    assert parsed["family_hex"] == "28"
    assert parsed["dialect_id"] == "input.nolf.idle_reply"


def test_lab_button_event_press():
    raw = bytes.fromhex("422d2f8185190000df03010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_hex"] == "2f8185df"
    assert parsed["id_wire_hex"] == "2f8185190000df"
    assert parsed["type_hex"] == "2d"
    assert parsed["dialect_id"] == "input.lab.button_event"


def test_nolf_button_event_press():
    raw = bytes.fromhex("4201dac46c100000c301010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_hex"] == "dac46cc3"
    assert parsed["id_wire_hex"] == "dac46c100000c3"
    assert parsed["type_hex"] == "01"
    assert parsed["dialect_id"] == "input.nolf.button_event"


def test_input_button_event_release():
    raw = bytes.fromhex("422d1e6a85190000af03000045")
    parsed = decode_input_payload(raw)
    assert parsed["action"] == "release"
    assert parsed["id_hex"] == "1e6a85af"


def test_input_button_event_marker_02():
    """Buttons with marker 0x02 (not only 0x03) — 2026-06-23 missing-buttons capture."""
    raw = bytes.fromhex("422de341851900001f02010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_hex"] == "e341851f"
    assert parsed["id_wire_hex"] == "e341851900001f"
    assert parsed["marker_hex"] == "02"


def test_unknown_type_is_still_routed():
    raw = bytes.fromhex("42aa2f8185190000df03010045")
    parsed = decode_input_payload(raw)
    assert parsed["family"] == "input_button_event"
    assert parsed["action"] == "press"
    assert parsed["id_hex"] == "2f8185df"
    assert parsed["type_hex"] == "aa"
    assert parsed["dialect_id"] == "input.unknown.button_event"


def test_input_button_event_rejects_bad_edge():
    assert decode_input_payload(bytes.fromhex("422de341851900001f02020045")) is None


def test_input_button_event_rejects_wrong_length():
    assert decode_input_payload(bytes.fromhex("422d2f8185190000df030100")) is None
    assert decode_input_payload(bytes.fromhex("422d2f8185190000df03010045ff")) is None
