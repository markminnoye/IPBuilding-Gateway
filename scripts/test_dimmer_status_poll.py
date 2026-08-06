#!/usr/bin/env python3
"""Dimmer on-demand status poll — ``I{ch}000000`` (Jan Nolf / IPBuilding 03.07).

Sends per-channel 8-byte queries to an IP0300PoE and prints ``I0154…`` replies.

Evidence: resources_and_docs/evidence/2026-08-05_dimmer_I_ch_000000_status_poll.md

Run:
    python3 scripts/test_dimmer_status_poll.py
    python3 scripts/test_dimmer_status_poll.py --dimmer 10.10.1.40 --repeat 3
"""

from __future__ import annotations

import argparse
import socket
import time

DIMMER_HOST_DEFAULT = "10.10.1.40"
DIMMER_PORT_DEFAULT = 1001
REPEAT_DEFAULT = 3
TIMEOUT_SEC = 1.5


def decode_i0154(data: bytes) -> str:
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return f"<hex {data.hex()}>"
    if text.startswith("I0154") and len(text) == 8:
        code = text[5:]
        if code == "999":
            return "idle/poll heartbeat (999)"
        ch, vv = code[0], code[1:]
        if vv == "00":
            pct = 0
        elif vv == "99":
            pct = 100
        else:
            try:
                pct = int(vv)
            except ValueError:
                pct = None
        return f"ch={ch} value_code={vv} → {pct}%"
    return text


def send_once(host: str, port: int, payload: bytes) -> tuple[bytes | None, float]:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT_SEC)
    t0 = time.monotonic()
    try:
        sock.sendto(payload, (host, port))
        data, _addr = sock.recvfrom(64)
        return data, (time.monotonic() - t0) * 1000
    except socket.timeout:
        return None, TIMEOUT_SEC * 1000
    finally:
        sock.close()


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dimmer", default=DIMMER_HOST_DEFAULT)
    ap.add_argument("--port", type=int, default=DIMMER_PORT_DEFAULT)
    ap.add_argument("--repeat", type=int, default=REPEAT_DEFAULT)
    args = ap.parse_args()

    print(f"Dimmer status poll — {args.dimmer}:{args.port} (repeat={args.repeat})")
    print()

    print("Baselines:")
    for payload, label in (
        (b"I9900", "idle keepalive"),
        (b"I0100", "5-byte I<CH>00 ch1 (no channel select)"),
    ):
        data, lat = send_once(args.dimmer, args.port, payload)
        decoded = decode_i0154(data) if data else "TIMEOUT"
        print(f"  {payload.decode():10s}  {data!r:14s}  {decoded}  ({lat:.1f}ms)  [{label}]")
        time.sleep(0.15)

    print()
    print("I{ch}000000 sweep:")
    for ch in range(8):
        payload = f"I{ch}000000".encode("ascii")
        replies: list[bytes | None] = []
        for _ in range(args.repeat):
            data, lat = send_once(args.dimmer, args.port, payload)
            replies.append(data)
            decoded = decode_i0154(data) if data else "TIMEOUT"
            print(f"  ch{ch} {payload.decode()}  {data!r:14s}  {decoded}  ({lat:.1f}ms)")
            time.sleep(0.15)
        uniq = {r for r in replies if r is not None}
        if len(uniq) == 1:
            print(f"       → stable: {decode_i0154(next(iter(uniq)))}")
        elif not uniq:
            print("       → all TIMEOUT")
        else:
            print(f"       → UNSTABLE: {[decode_i0154(u) for u in sorted(uniq)]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
