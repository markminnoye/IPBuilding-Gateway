"""Dimmer UDP/1001 payload encoder/decoder.

## Hub→dimmer dialect (gateway sends this)

Command frames: ``<S|C><channel><value_code>1030``

- ``S`` = set/dim to level, ``C`` = cut/off
- ``<channel>`` = single digit 0–7
- ``<value_code>`` = ``10``..``98`` for 10–98 %, ``99`` = 100 %, ``00`` = off

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

## Input-module→dimmer dialect (peer-to-peer)

The IP1100PoE input module sends commands **directly** to the IP0300PoE dimmer,
bypassing the hub entirely — the regular IPBox switch path. When the gateway
replaces the hub it becomes the source of these frames, so this dialect is both
**decoded** here (observability / passthrough logging) and **encoded** for
downstream button control (see ``encode_dim_toggle`` / ``encode_dim_start`` /
``encode_dim_stop`` and the ``TOGGLE`` / ``DIM_START`` / ``DIM_STOP`` API actions).

Command frames (suffix differs from the hub ``…1030`` dialect):

- ``T<channel><value>1000`` — toggle (short press; module uses last-level memory)
- ``D<channel><value>1003`` — dim hold start (auto-direction; no ack from dimmer)
- ``D<channel><value>1000`` — dim hold stop (dimmer replies ``I0154<ch><vv>``)

Hold = start/stop protocol: the dimmer ramps autonomously between the two
packets. Direction alternates internally on each successive hold — the same wire
payload serves dim-up and dim-down, and the value field is a fixed placeholder.
Evidence: ``resources_and_docs/evidence/2026-06-22_dimmer_p2p_hold_dim_capture.md``.
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

# Input-module peer-to-peer dialect (IP1100PoE → IP0300PoE, observed only).
_INPUT_TOGGLE_RE = re.compile(r"^T(?P<channel>\d)(?P<dimmax>\d{2})1000$")
_INPUT_DIM_START_RE = re.compile(r"^D(?P<channel>\d)(?P<dimmax>\d{2})1003$")
_INPUT_DIM_STOP_RE = re.compile(r"^D(?P<channel>\d)(?P<dimmax>\d{2})1000$")


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

    # Input-module peer-to-peer dialect — decoded for observability only.
    m = _INPUT_TOGGLE_RE.match(text)
    if m:
        return {
            "family": "input_p2p_toggle",
            "channel": int(m.group("channel")),
            "dimmax": int(m.group("dimmax")),
            "raw": text,
        }

    m = _INPUT_DIM_START_RE.match(text)
    if m:
        return {
            "family": "input_p2p_dim_start",
            "channel": int(m.group("channel")),
            "dimmax": int(m.group("dimmax")),
            "raw": text,
        }

    m = _INPUT_DIM_STOP_RE.match(text)
    if m:
        return {
            "family": "input_p2p_dim_stop",
            "channel": int(m.group("channel")),
            "dimmax": int(m.group("dimmax")),
            "raw": text,
        }

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


def encode_dim_toggle(channel: int) -> bytes:
    """Encode hub→dimmer button toggle: T<ch>991000.

    Short-press semantics: the module flips between off and the last
    non-zero level stored in its local memory. The ``99`` value field is a
    fixed placeholder — the dimmer ignores it for this dialect and replies
    with ``I0154<ch><VV>`` reporting the new level.
    """
    return f"T{channel}991000".encode("ascii")


def encode_dim_start(channel: int) -> bytes:
    """Encode hub→dimmer hold-to-dim **start**: D<ch>001003.

    No reply is produced; the module begins ramping and reverses direction
    on each successive hold (it owns the direction state). The ``00`` value
    field is a fixed placeholder.
    """
    return f"D{channel}001003".encode("ascii")


def encode_dim_stop(channel: int) -> bytes:
    """Encode hub→dimmer hold-to-dim **stop**: D<ch>001000.

    Pauses the ramp started by :func:`encode_dim_start`; the dimmer replies
    with ``I0154<ch><VV>`` reporting the level reached when the stop landed.
    """
    return f"D{channel}001000".encode("ascii")
