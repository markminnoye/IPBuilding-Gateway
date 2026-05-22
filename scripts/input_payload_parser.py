#!/usr/bin/env python3
"""Parse IPBuilding IP1100 input module UDP/1001 payloads (proto-map v0.1).

Confirmed:
  Hub poll:     I0000 (4-byte ASCII)
  Idle reply:   I\\x02R...E (14-byte binary)
  Button event: B-...E (13-byte) — 10:25.pcapng mirror 7<-13
"""

from __future__ import annotations

import argparse
import json
import sys
from typing import Any

from gateway.payloads.input import decode_input_payload as parse_input_payload


def _run_self_test() -> int:
    idle_reply = bytes([0x49, 0x02, 0x52, 0x05, 0x02, 0x04, 0, 0, 0, 0, 0, 0, 0, 0x45])
    press_event = bytes.fromhex("422d2f8185190000df03010045")
    tests: list[tuple[bytes | str, dict[str, Any]]] = [
        (b"I0000", {"family": "input_poll", "action": "poll"}),
        (idle_reply, {"family": "input_reply_binary", "status_byte_0": 0x05}),
        (press_event, {"family": "input_button_event", "action": "press"}),
    ]
    for payload, expected in tests:
        got = parse_input_payload(payload)
        if not got:
            print(f"FAIL: expected parse for {payload!r}", file=sys.stderr)
            return 1
        for key, value in expected.items():
            if got.get(key) != value:
                print(f"FAIL: {payload!r} expected {key}={value!r}, got {got.get(key)!r}", file=sys.stderr)
                return 1
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description="Parse IP1100 input UDP payloads.")
    parser.add_argument("payload_hex", nargs="*", help="Hex string(s), e.g. 49025205020400000000000045")
    parser.add_argument("--self-test", action="store_true")
    args = parser.parse_args()

    if args.self_test:
        return _run_self_test()

    for hx in args.payload_hex or [line.strip() for line in sys.stdin if line.strip()]:
        raw = bytes.fromhex(hx.replace(" ", ""))
        parsed = parse_input_payload(raw)
        print(json.dumps({"hex": hx, "parsed": parsed}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
