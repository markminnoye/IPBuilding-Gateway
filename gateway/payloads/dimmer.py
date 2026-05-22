"""Dimmer UDP/1001 payload encoder/decoder (no J separator; I0154xxx replies)."""

from __future__ import annotations

import re
from typing import Any

from gateway.models import DimmerCommand, DimmerStatus

_DIMMER_CMD_RE = re.compile(r"^(?P<prefix>[SC])(?P<channel>\d)(?P<value>\d{2})1030$")
_DIMMER_IDLE_RE = re.compile(r"^I9900$")
_DIMMER_REPLY_RE = re.compile(r"^I01(?P<family>54)(?P<value_code>\d{3})$")


def _percent_to_value_code(level: int) -> str:
    if level <= 0:
        return "00"
    if level >= 100:
        return "99"
    return f"{level:02d}"


def _value_code_to_percent(code: str) -> int | None:
    try:
        n = int(code)
    except ValueError:
        return None
    if n == 0:
        return 0
    if n == 99:
        return 100
    if 10 <= n <= 90:
        return n
    if n == 100:
        return 100
    return n  # best-effort for codes like 150, 170


def decode_dimmer_payload(data: bytes) -> dict[str, Any] | None:
    try:
        text = data.decode("ascii").strip()
    except UnicodeDecodeError:
        return None

    m = _DIMMER_REPLY_RE.match(text)
    if m:
        code = m.group("value_code")
        return {
            "family": "dimmer_status_reply",
            "device_type": "01",
            "family_constant": m.group("family"),
            "internal_value_code": code,
            "level_percent": _value_code_to_percent(code),
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
