#!/usr/bin/env python3
"""Parse IPBuilding relay UDP payload ASCII according to proto-map v0.3.

Status (`I<module><channel><state>`): in lab captures only `0100` (= ON) and `0000`
(= OFF) have been observed as `state` quartets. Other quartets may exist but were
**not** seen in UDP/1001 inventory across golden + relay sweep pcaps (2026-05-04).

`P000000000` (10 ASCII chars): relay → hub (or relay → IPBox home leg) **fixed-width echo**
of the hub → relay `P0000` pulse; sub-5 ms follow-up when both directions appear in one export
(`captures/2026-05-05T1040Z_user-full-capture/`). Same nine digits all zero ⇒ same channel-0 pulse
as `P0000` (see `resources_and_docs/evidence/2026-05-04_relay_payload_correlation.md` addendum 2026-05-15).

Examples:
  S0000 -> set channel 0 ON
  T1400 -> toggle channel 14
  C0000 -> clear/off channel 0
  P0000 -> pulse channel 0
  C1600 -> clear/off channel 16
  C1700 -> clear/off channel 17
  C0200 -> clear/off channel 2
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

_RELAY_CMD_RE = re.compile(r"^(?P<prefix>[SCTP])(?P<channel>\d{2})00$")
_RELAY_STATUS_RE = re.compile(r"^I(?P<module>\d{3})(?P<channel>\d{2})(?P<state>\d{4})$")
_RELAY_REPLY_PULSE_RE = re.compile(r"^P\d{9}$")

def parse_relay_payload_ascii(payload: str) -> dict[str, Any] | None:
    """Return structured fields for a relay payload, else None."""
    raw = payload.strip()
    if not raw:
        return None

    m = _RELAY_CMD_RE.match(raw)
    if m:
        prefix = m.group("prefix")
        channel = int(m.group("channel"))
        action_map = {
            "S": "on",
            "T": "toggle",
            "C": "off",
            "P": "pulse",
        }
        return {
            "raw": raw,
            "family": "relay_command",
            "action": action_map.get(prefix),
            "channel": channel,
            "suffix": "00",
            "proto_map": "v0.2",
        }

    m = _RELAY_STATUS_RE.match(raw)
    if m:
        channel = int(m.group("channel"))
        state_code = m.group("state")
        if state_code == "0100":
            state = "on"
        elif state_code == "0000":
            state = "off"
        else:
            state = "unknown"
        return {
            "raw": raw,
            "family": "relay_status",
            "action": "status",
            "module": m.group("module"),
            "channel": channel,
            "state_code": state_code,
            "state": state,
            "proto_map": "v0.2",
        }

    m = _RELAY_REPLY_PULSE_RE.match(raw)
    if m:
        nine = raw[1:]
        out: dict[str, Any] = {
            "raw": raw,
            "family": "relay_reply_candidate",
            "action": "pulse_reply_candidate",
            "proto_map": "v0.3",
            "suffix_nine": nine,
            "note": (
                "Relay-side fixed-width echo of hub P0000 pulse when return path is visible; "
                "timing ~2 ms after hub P0000 in 2026-05-05T1040Z_user-full-capture."
            ),
        }
        if nine == "000000000":
            out["hub_command_ascii"] = "P0000"
            out["pulse_channel"] = 0
        return out

    return None

def _run_self_test() -> int:
    tests = [
        ("S0000", {"family": "relay_command", "action": "on", "channel": 0}),
        ("T1400", {"family": "relay_command", "action": "toggle", "channel": 14}),
        ("C0000", {"family": "relay_command", "action": "off", "channel": 0}),
        ("P0000", {"family": "relay_command", "action": "pulse", "channel": 0}),
        ("C1600", {"family": "relay_command", "action": "off", "channel": 16}),
        ("C1700", {"family": "relay_command", "action": "off", "channel": 17}),
        ("C0200", {"family": "relay_command", "action": "off", "channel": 2}),
        ("I000120100", {"family": "relay_status", "action": "status", "channel": 12, "state": "on"}),
        ("I000000000", {"family": "relay_status", "action": "status", "channel": 0, "state": "off"}),
        (
            "P000000000",
            {
                "family": "relay_reply_candidate",
                "action": "pulse_reply_candidate",
                "proto_map": "v0.3",
                "hub_command_ascii": "P0000",
                "pulse_channel": 0,
            },
        ),
        (
            "P123456789",
            {
                "family": "relay_reply_candidate",
                "suffix_nine": "123456789",
            },
        ),
    ]
    for payload, expected in tests:
        got = parse_relay_payload_ascii(payload)
        if not got:
            print(f"FAIL: expected parse for {payload}", file=sys.stderr)
            return 1
        for key, value in expected.items():
            if got.get(key) != value:
                print(f"FAIL: {payload} expected {key}={value!r}, got {got.get(key)!r}", file=sys.stderr)
                return 1
    no_equiv = parse_relay_payload_ascii("P123456789")
    if no_equiv and "hub_command_ascii" in no_equiv:
        print("FAIL: P123456789 must not set hub_command_ascii", file=sys.stderr)
        return 1
    print("self-test ok")
    return 0

def main() -> int:
    parser = argparse.ArgumentParser(description="Parse IPBuilding relay payload ASCII strings.")
    parser.add_argument("payload", nargs="*", help="Payload string(s), e.g. S0000")
    parser.add_argument("--self-test", action="store_true", help="Run built-in parser checks.")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    payloads = args.payload or [line.strip() for line in sys.stdin if line.strip()]
    for payload in payloads:
        parsed = parse_relay_payload_ascii(payload)
        print(json.dumps({"payload": payload, "parsed": parsed}, ensure_ascii=False))
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
