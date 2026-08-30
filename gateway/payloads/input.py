"""IP1100 input module UDP/1001 payloads.

Confirmed: hub poll I0000; idle reply I\\x02<family>…E (13 or 14 bytes).
Button event: B<type>…E (13 bytes) — lab type 0x2d, Nolf type 0x01.
"""

from __future__ import annotations

import re
from typing import Any

from gateway.button_id import canonical_button_id
from gateway.models import InputEvent

_INPUT_POLL_RE = re.compile(rb"^I0000$")
_INPUT_REPLY_RE = re.compile(
    rb"^I\x02(?P<family>.)(?P<status>.{3})\x00{6,7}E$"
)
# 13-byte event: B + type + 7-byte id + marker + edge + 0x00 + E
# marker observed as 0x03 (Sprint 5) and 0x02 (2026-06-23); accept any byte.
_INPUT_EVENT_RE = re.compile(
    rb"^B(?P<type>.)(?P<id>.{7})(?P<marker>.)(?P<edge>\x01|\x00)\x00E$"
)

_BUTTON_TYPE_DIALECT = {
    0x2D: "input.lab.button_event",
    0x01: "input.nolf.button_event",
}
_IDLE_FAMILY_DIALECT = {
    0x52: "input.lab.idle_reply",  # 'R'
    0x28: "input.nolf.idle_reply",
}

UNKNOWN_BUTTON_DIALECT = "input.unknown.button_event"


def encode_input_poll() -> bytes:
    """Hub→input keepalive poll."""
    return b"I0000"


def decode_input_payload(data: bytes) -> dict[str, Any] | None:
    if _INPUT_POLL_RE.match(data):
        return {
            "family": "input_poll",
            "action": "poll",
            "direction": "hub_to_input",
        }

    m = _INPUT_REPLY_RE.match(data)
    if m:
        status = m.group("status")
        family = m.group("family")
        family_byte = family[0]
        return {
            "family": "input_reply_binary",
            "action": "status_reply",
            "direction": "input_to_hub",
            "status_bytes_hex": status.hex(),
            "status_byte_0": status[0],
            "status_byte_1": status[1],
            "status_byte_2": status[2],
            "family_hex": family.hex(),
            "family_byte": family_byte,
            "dialect_id": _IDLE_FAMILY_DIALECT.get(
                family_byte, "input.unknown.idle_reply"
            ),
            "length": len(data),
        }

    m = _INPUT_EVENT_RE.match(data)
    if m:
        edge = m.group("edge")
        type_byte = m.group("type")[0]
        id_wire_hex = m.group("id").hex()
        id_hex = canonical_button_id(id_wire_hex) or id_wire_hex
        return {
            "family": "input_button_event",
            "action": "press" if edge == b"\x01" else "release",
            "direction": "input_to_hub",
            "id_hex": id_hex,
            "id_wire_hex": id_wire_hex,
            "type_hex": f"{type_byte:02x}",
            "dialect_id": _BUTTON_TYPE_DIALECT.get(
                type_byte, UNKNOWN_BUTTON_DIALECT
            ),
            "marker_hex": m.group("marker").hex(),
            "length": len(data),
        }

    return None


def decode_input_event(data: bytes) -> InputEvent | None:
    parsed = decode_input_payload(data)
    if not parsed:
        return None
    if parsed.get("family") == "input_reply_binary":
        return InputEvent(
            event_type="idle_status",
            status_bytes_hex=parsed.get("status_bytes_hex"),
        )
    if parsed.get("family") == "input_button_event":
        return InputEvent(
            event_type=parsed.get("action", "unknown"),
            status_bytes_hex=parsed.get("id_hex"),
        )
    return None
