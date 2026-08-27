"""Dimmer UDP/1001 payload encoder/decoder.

Operator choice (aan/uit vs dim %): see
``resources_and_docs/2026-05-17_ipbuilding_fieldbus_capability_matrix.md``
§ "Dimmer: welk commando wanneer?".

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

On-demand per-channel status query (IPBox / IPBuilding 03.07 controle):
``I{ch}000000`` (8 ASCII bytes, channel digit 0–7) → reply ``I0154{ch}{vv}``.
Distinct from the 5-byte idle keepalive ``I9900`` (always ``I0154999``) and
from relay-style ``I<CH>00`` (no channel select on dimmer). Evidence:
``resources_and_docs/evidence/2026-08-05_dimmer_I_ch_000000_status_poll.md``.

Confirmed against the REST↔UDP correlation for the Bureau dimmer (ch1, comp
572): ``OFF→I0154100``, ``DIM 30→I0154130``, ``DIM 70→I0154170``,
``DIM 100→I0154199``, idle ``→I0154999``.  See
``resources_and_docs/evidence/2026-05-14_dimmer_rest_udp_timeline_writeup.md``.

### OFF is family-dependent

Family ``54`` (lab IP0300PoE) treats ``C`` as cut and ignores the value field —
lab confirms both ``C<ch>991030`` and ``C<ch>001030`` fade to off. Family ``15``
(Nolf-generation) appears to execute the value: ``C<ch>991030`` lands as
**100 %** (HA shows off, lamp goes full). First hypothesis to field-test:
``C<ch>001030`` (cut with value ``00``). Only if that fails, fall back to a
set-to-0. Pick the encoding with :data:`DIM_OFF_STYLE_BY_FAMILY`.

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
_DIMMER_STATUS_POLL_RE = re.compile(r"^I(?P<channel>[0-7])000000$")
_DIMMER_REPLY_RE = re.compile(r"^I01(?P<family>54|15)(?P<value_code>\d{3})$")

# Idle/poll heartbeat is family-scoped: 999 only for lab family 54, 000 only
# for Nolf family 15. Do not treat 000 as a global sentinel — I0154000 is a
# valid lab ch0-off after C0….
_DIMMER_IDLE_CODE_BY_FAMILY = {"54": "999", "15": "000"}
_DIMMER_STATUS_DIALECT_BY_FAMILY = {
    "54": "dimmer.lab.status_reply",
    "15": "dimmer.nolf.status_reply",
}
_DIMMER_IDLE_DIALECT_BY_FAMILY = {
    "54": "dimmer.lab.idle_keepalive",
    "15": "dimmer.nolf.idle_keepalive",
}

# OFF encodings. Lab modules read ``C`` as cut and ignore the value (lab
# 2026-08-27: ``C1991030`` and ``C1001030`` both fade to off). Nolf symptom
# with ``C…99…`` is full brightness — try ``C…00…`` first before an ``S…00…``
# workaround. Field evidence:
# resources_and_docs/evidence/2026-08-26_jan_nolf_165_field_test.md.
DIM_OFF_CUT = "cut"
DIM_OFF_ZERO = "zero"
DIM_OFF_STYLES = (DIM_OFF_CUT, DIM_OFF_ZERO)

# Reply family constant → OFF encoding that family understands.
DIM_OFF_STYLE_BY_FAMILY = {"54": DIM_OFF_CUT, "15": DIM_OFF_ZERO}

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
        family = m.group("family")
        code = m.group("value_code")  # 3 digits: <channel><value_code>
        if code == _DIMMER_IDLE_CODE_BY_FAMILY.get(family):
            result = {
                "family": "dimmer_poll",
                "action": "idle",
                "family_constant": family,
                "internal_value_code": code,
                "raw": text,
            }
            dialect_id = _DIMMER_IDLE_DIALECT_BY_FAMILY.get(family)
            if dialect_id:
                result["dialect_id"] = dialect_id
            return result
        channel = int(code[0])
        value_code = code[1:]
        return {
            "dialect_id": _DIMMER_STATUS_DIALECT_BY_FAMILY[family],
            "family": "dimmer_status_reply",
            "device_type": "01",
            "family_constant": family,
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
        # encode_dim_off sends placeholder 99 in C{ch}991030; the C prefix
        # means off, so level_percent is 0. value_code stays "99" on the wire.
        level_percent = (
            0 if prefix == "C" else _value_code_to_percent(value_code)
        )
        return {
            "family": "dimmer_command",
            "action": "set" if prefix == "S" else "off",
            "channel": int(m.group("channel")),
            "value_code": value_code,
            "level_percent": level_percent,
            "raw": text,
        }

    if _DIMMER_IDLE_RE.match(text):
        return {"family": "dimmer_poll", "action": "idle", "raw": text}

    m = _DIMMER_STATUS_POLL_RE.match(text)
    if m:
        return {
            "family": "dimmer_status_poll",
            "action": "status_query",
            "channel": int(m.group("channel")),
            "direction": "hub_to_dimmer",
            "raw": text,
        }

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


def encode_dimmer_status_poll(channel: int) -> bytes:
    """Encode hub→dimmer on-demand status read: ``I{ch}000000``.

    Reply is ``I0154{ch}{vv}`` with the live level for that channel.
    Channel must be 0–7. See RE evidence 2026-08-05.
    """
    if not 0 <= channel <= 7:
        raise ValueError(f"dimmer channel must be 0–7, got {channel}")
    return f"I{channel}000000".encode("ascii")


def encode_dim_command(cmd: DimmerCommand) -> bytes:
    """Encode hub→dimmer DIM command: S<ch><value_code>1030."""
    code = _percent_to_value_code(cmd.level)
    wire = f"S{cmd.channel}{code}1030".encode("ascii")
    return wire


def resolve_dim_off_style(configured: str, family: str | None) -> str:
    """Pick the OFF encoding for one dimmer module.

    An explicit ``configured`` style wins over everything. Otherwise the reply
    family the module answered with decides; a module that has not answered yet
    falls back to the lab encoding.
    """
    if configured in DIM_OFF_STYLES:
        return configured
    return DIM_OFF_STYLE_BY_FAMILY.get(family or "", DIM_OFF_CUT)


def encode_dim_off(channel: int, *, style: str = DIM_OFF_CUT) -> bytes:
    """Encode hub→dimmer OFF.

    ``cut`` → ``C<ch>991030`` — the frame the IPBox itself sends on lab
    hardware. ``zero`` → ``C<ch>001030`` — same cut prefix with value ``00``
    (lab-proven equivalent to cut+99; preferred first try for Nolf modules
    that treat ``99`` as 100 %). See :data:`DIM_OFF_STYLES`.
    """
    if style == DIM_OFF_ZERO:
        return f"C{channel}001030".encode("ascii")
    if style != DIM_OFF_CUT:
        raise ValueError(f"unknown dimmer off style: {style!r}")
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
