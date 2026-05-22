#!/usr/bin/env python3
"""Parse IPBuilding dimmer UDP payload ASCII according to proto-map v0.1.

Examples:
  S0501030 -> set channel 0 value 50
  C1991030 -> off/cut channel 1 value code 99
  I9900    -> idle/poll marker
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from typing import Any

_SET_OR_CUT_RE = re.compile(r"^(?P<prefix>[SC])(?P<channel>\d)(?P<value>\d{2})1030$")
_IDLE_RE = re.compile(r"^I(?P<code>\d{4})$")


def parse_dimmer_payload_ascii(payload: str) -> dict[str, Any] | None:
    """Return structured fields for a dimmer payload, else None."""
    raw = payload.strip()
    if not raw:
        return None

    m = _SET_OR_CUT_RE.match(raw)
    if m:
        prefix = m.group("prefix")
        value_code = int(m.group("value"))
        value_percent = 100 if value_code == 99 else value_code
        return {
            "raw": raw,
            "family": "dimmer_command",
            "action": "set" if prefix == "S" else "off",
            "channel": int(m.group("channel")),
            "value_code": value_code,
            "value_percent": value_percent,
            "suffix": "1030",
            "proto_map": "v0.1",
        }

    m = _IDLE_RE.match(raw)
    if m:
        return {
            "raw": raw,
            "family": "poll_or_status",
            "action": "idle",
            "code": m.group("code"),
            "proto_map": "v0.1",
        }

    return None


def _run_self_test() -> int:
    tests = [
        ("S0501030", {"action": "set", "channel": 0, "value_percent": 50}),
        ("S1991030", {"action": "set", "channel": 1, "value_percent": 100}),
        ("C2991030", {"action": "off", "channel": 2, "value_percent": 100}),
        ("I9900", {"action": "idle", "family": "poll_or_status"}),
    ]
    for payload, expected in tests:
        got = parse_dimmer_payload_ascii(payload)
        if not got:
            print(f"FAIL: expected parse for {payload}", file=sys.stderr)
            return 1
        for key, value in expected.items():
            if got.get(key) != value:
                print(f"FAIL: {payload} expected {key}={value!r}, got {got.get(key)!r}", file=sys.stderr)
                return 1
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse IPBuilding dimmer payload ASCII strings.")
    parser.add_argument("payload", nargs="*", help="Payload string(s), e.g. S0501030")
    parser.add_argument("--self-test", action="store_true", help="Run built-in parser checks.")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    payloads = args.payload or [line.strip() for line in sys.stdin if line.strip()]
    for payload in payloads:
        parsed = parse_dimmer_payload_ascii(payload)
        print(json.dumps({"payload": payload, "parsed": parsed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
