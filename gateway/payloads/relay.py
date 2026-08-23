"""Relay UDP/1001 payload encoder/decoder (raw ASCII on UDP/1001)."""

from __future__ import annotations

import re
from typing import Any

from gateway.models import RelayAction, RelayCommand, RelayStatus

_RELAY_CMD_RE = re.compile(r"^(?P<prefix>[SCTP])(?P<channel>\d{2})00$")
_RELAY_STATUS_RE = re.compile(r"^I(?P<module>\d{3})(?P<channel>\d{2})(?P<state>\d{4})$")
_RELAY_STATUS_SHORT_RE = re.compile(r"^I(?P<channel>\d{4})(?P<state>\d{4})$")
_RELAY_REPLY_PULSE_RE = re.compile(r"^P\d{9}$")
_J_ENVELOPE_RE = re.compile(r"^.(?P<core>[SCPT]\d{4,5})$")

# Prefix-byte → first command letter mapping (Sprint 2 confirmed)
# Sprint 2 confirmed action letters
_CMD_LETTER: dict[RelayAction, str] = {
    RelayAction.ON: "S",
    RelayAction.OFF: "C",
    RelayAction.PULSE: "P",
    RelayAction.TOGGLE: "T",
}


def relay_state_from_code(state_code: str) -> str:
    """Map a 4-digit ASCII state quartet to on/off/unknown.

    Prefix rule (hypothesized from Nolf IP0200 Diagnostic 03.03):
    ``01xx`` → on, ``00xx`` → off. Lab firmware uses ``0100``/``0000``;
    older modules also report ``0115``/``0015`` on status-poll. Command
    replies on those modules still use ``0100``/``0000``. The raw
    ``state_code`` is kept on the northbound object.
    """
    if len(state_code) == 4 and state_code.isdigit():
        if state_code.startswith("01"):
            return "on"
        if state_code.startswith("00"):
            return "off"
    return "unknown"


def strip_j_envelope(data: bytes) -> bytes:
    """Strip optional [1-byte prefix] + 'J' wrapper from hub→relay wire form."""
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return data
    if len(text) >= 3 and text[1] == "J":
        return text[2:].encode("ascii")
    m = _J_ENVELOPE_RE.match(text)
    if m:
        return m.group("core").encode("ascii")
    return data


def decode_relay_payload(data: bytes) -> dict[str, Any] | None:
    """Decode relay ASCII payload (core or wire envelope)."""
    core = strip_j_envelope(data)
    try:
        text = core.decode("ascii").strip()
    except UnicodeDecodeError:
        return None

    m = _RELAY_CMD_RE.match(text)
    if m:
        prefix = m.group("prefix")
        action_map = {"S": "on", "T": "toggle", "C": "off", "P": "pulse"}
        return {
            "family": "relay_command",
            "action": action_map.get(prefix),
            "channel": int(m.group("channel")),
            "raw": text,
        }

    m = _RELAY_STATUS_RE.match(text)
    if m:
        state_code = m.group("state")
        state = relay_state_from_code(state_code)
        return {
            "family": "relay_status",
            "channel": int(m.group("channel")),
            "module": m.group("module"),
            "state": state,
            "state_code": state_code,
            "raw": text,
        }

    m = _RELAY_STATUS_SHORT_RE.match(text)
    if m:
        state_code = m.group("state")
        state = relay_state_from_code(state_code)
        return {
            "family": "relay_status",
            "channel": int(m.group("channel")),
            "module": None,
            "state": state,
            "state_code": state_code,
            "raw": text,
        }

    if _RELAY_REPLY_PULSE_RE.match(text):
        return {
            "family": "relay_reply_candidate",
            "action": "pulse_reply",
            "raw": text,
            "suffix_nine": text[1:],
        }

    return None


def decode_relay_status(data: bytes) -> RelayStatus | None:
    parsed = decode_relay_payload(data)
    if not parsed or parsed.get("family") != "relay_status":
        return None
    return RelayStatus(
        channel=parsed["channel"],
        state=parsed["state"],
        state_code=parsed["state_code"],
        module=parsed.get("module"),
    )


def encode_relay_command(cmd: RelayCommand) -> bytes:
    """Encode hub→relay command as raw ASCII (no envelope wrapper).

    Relay module expects raw ASCII commands directly on UDP/1001:
      S{ch}00  — ON
      C{ch}00  — OFF
      T{ch}00  — toggle
      P{ch}00  — pulse
    Reply is always a status line like I000030100 (on) or I000030000 (off).
    """
    ch = f"{cmd.channel:02d}"
    letter = _CMD_LETTER.get(cmd.action, "T")
    if cmd.action == RelayAction.PULSE and cmd.channel == 0:
        core = "P0000"
    else:
        core = f"{letter}{ch}00"
    return core.encode("ascii")


def encode_hub_to_relay(cmd: RelayCommand) -> bytes:
    """Alias for encode_relay_command."""
    return encode_relay_command(cmd)


def encode_relay_status_poll(channel: int) -> bytes:
    """Encode hub→relay on-demand status read (IPBox cold-boot sweep format).

    Query ``I<CH>00`` (5 bytes ASCII) returns ``I000<CH><state>`` where
    the first two digits of the state quartet are on/off (``01xx`` = on,
    ``00xx`` = off). Lab firmware uses ``0100``/``0000``; older Nolf
    IP0200 modules also report ``0115``/``0015`` on this poll. See RE
    evidence 2026-06-12 and 2026-08-08.
    """
    return f"I{channel:02d}00".encode("ascii")
