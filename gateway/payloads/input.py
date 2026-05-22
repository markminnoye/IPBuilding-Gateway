"""IP1100 input module UDP/1001 payloads.

Confirmed: hub poll I0000; idle reply I\\x02R...E (14 bytes).
Button event: B-…E (13 bytes) — evidence captures/2026-05-22T102500Z_sprint5-manual-10-25.
"""

from __future__ import annotations

import re
from typing import Any

from gateway.models import InputEvent

_INPUT_POLL_RE = re.compile(rb"^I0000$")
_INPUT_REPLY_RE = re.compile(rb"^I\x02R(?P<status>.{3})\x00{7}E$")
# 13-byte event: B + '-' + 6-byte id core + 1-byte id suffix + 0x03 + edge + 0x00 + E
_INPUT_EVENT_RE = re.compile(
    rb"^B\x2d(?P<id_core>.{6})(?P<id_suffix>.)\x03(?P<edge>\x01|\x00)\x00E$"
)


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
        return {
            "family": "input_reply_binary",
            "action": "status_reply",
            "direction": "input_to_hub",
            "status_bytes_hex": status.hex(),
            "status_byte_0": status[0],
            "status_byte_1": status[1],
            "status_byte_2": status[2],
            "length": len(data),
        }

    m = _INPUT_EVENT_RE.match(data)
    if m:
        edge = m.group("edge")
        return {
            "family": "input_button_event",
            "action": "press" if edge == b"\x01" else "release",
            "direction": "input_to_hub",
            "id_core_hex": m.group("id_core").hex(),
            "id_suffix_hex": m.group("id_suffix").hex(),
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
            status_bytes_hex=f"{parsed.get('id_core_hex')}{parsed.get('id_suffix_hex')}",
        )
    return None
