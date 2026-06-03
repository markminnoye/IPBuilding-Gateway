"""Dimmer UDP/1001 payload encoder/decoder.

Reply frames are 8 ASCII bytes ``I0154<C><VV>`` where:

- ``<C>``   single channel digit (0-7), matching the commanded channel.
- ``<VV>``  2-digit value code: ``00`` = OFF, ``10``..``98`` = that percent,
            ``99`` = 100% (full).

The all-nines code ``999`` is an idle/poll heartbeat — it carries no channel
and no setpoint, so it must not be interpreted as a level.

Confirmed against the REST↔UDP correlation for the Bureau dimmer (ch1, comp
572): ``OFF→I0154100``, ``DIM 30→I0154130``, ``DIM 70→I0154170``,
``DIM 100→I0154199``, idle ``→I0154999``.  See
``resources_and_docs/evidence/2026-05-14_dimmer_rest_udp_timeline_writeup.md``.
"""

from __future__ import annotations

import re
from typing import Any

from gateway.models import DimmerCommand, DimmerStatus

_DIMMER_CMD_RE = re.compile(r"^(?P<prefix>[SC])(?P<channel>\d)(?P<value>\d{2})1030$")
_DIMMER_IDLE_RE = re.compile(r"^I9900$")
_DIMMER_REPLY_RE = re.compile(r"^I01(?P<family>54)(?P<value_code>\d{3})$")

# All-nines reply code = idle/poll heartbeat, not a per-channel setpoint.
_DIMMER_IDLE_CODE = "999"


def _percent_to_value_code(level: int) -> str:
    if level <= 0:
        return "00"
    if level >= 100:
        return "99"
    return f"{level:02d}"


def _value_code_to_percent(code: str) -> int | None:
    """Map a 2-digit value code to a percent.

    ``00`` = off (0%), ``99`` = full (100%), anything in between is the
    literal percent.
    """
    try:
        n = int(code)
    except ValueError:
        return None
    if n <= 0:
        return 0
    if n >= 99:
        return 100
    return n


def decode_dimmer_payload(data: bytes) -> dict[str, Any] | None:
    try:
        text = data.decode("ascii").strip()
    except UnicodeDecodeError:
        return None

    m = _DIMMER_REPLY_RE.match(text)
    if m:
        code = m.group("value_code")  # 3 digits: <channel><value_code>
        if code == _DIMMER_IDLE_CODE:
            return {
                "family": "dimmer_poll",
                "action": "idle",
                "internal_value_code": code,
                "raw": text,
            }
        channel = int(code[0])
        value_code = code[1:]
        return {
            "family": "dimmer_status_reply",
            "device_type": "01",
            "family_constant": m.group("family"),
            "channel": channel,
            "internal_value_code": code,
            "value_code": value_code,
            "level_percent": _value_code_to_percent(value_code),
            "raw": text,
        }

    m = _DIMMER_CMD_RE.match(text)
    if m:
        prefix = m.group("prefix")
        value_code = m.group("value")
        return {
            "family": "dimmer_command",
            "action": "set" if prefix == "S" else "off",
            "channel": int(m.group("channel")),
            "value_code": value_code,
            "level_percent": _value_code_to_percent(value_code),
            "raw": text,
        }

    if _DIMMER_IDLE_RE.match(text):
        return {"family": "dimmer_poll", "action": "idle", "raw": text}

    return None


def decode_dimmer_status(data: bytes) -> DimmerStatus | None:
    parsed = decode_dimmer_payload(data)
    if not parsed or parsed.get("family") != "dimmer_status_reply":
        return None
    return DimmerStatus(
        channel=parsed.get("channel"),
        internal_value_code=parsed["internal_value_code"],
        level_percent=parsed.get("level_percent"),
        device_type=parsed.get("device_type", "01"),
        family_constant=parsed.get("family_constant", "54"),
    )


def encode_dim_command(cmd: DimmerCommand) -> bytes:
    """Encode hub→dimmer DIM command: S<ch><value_code>1030."""
    code = _percent_to_value_code(cmd.level)
    wire = f"S{cmd.channel}{code}1030".encode("ascii")
    return wire


def encode_dim_off(channel: int) -> bytes:
    """Encode hub→dimmer OFF: C<ch>991030 (value 99 = OFF pattern from sweep)."""
    return f"C{channel}991030".encode("ascii")
