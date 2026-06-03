#!/usr/bin/env python3
"""Relay poll payload test — I<ch> vs P0000 reply behavior.

Tests whether relay module 10.10.1.30 responds to I<ch> polls with
channel status replies (I<CH><state>), or only to P0000 with pulse echo.

Run:
    python3 scripts/test_relay_poll.py [--relay HOST] [--port PORT] [--repeat N]

No args: uses 10.10.1.30:1001, repeat=3.
"""

import argparse
import socket
import struct
import time
import sys

RELAY_HOST_DEFAULT = "10.10.1.30"
RELAY_PORT_DEFAULT = 1001
REPEAT_DEFAULT = 3
TIMEOUT_SEC = 2.0

PAYLOADS = [
    ("P0000",     "baseline pulse poll ch 0"),
    ("I0000",     "I-poll channel 0"),
    ("I0010",     "I-poll channel 10"),
    ("I0016",     "I-poll channel 16"),
    ("I0023",     "I-poll channel 23"),
]


def send_poll(host: str, port: int, payload: str) -> tuple[bytes | None, float]:
    """Send poll payload, return (reply_bytes, latency_ms)."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(TIMEOUT_SEC)
    data = payload.encode("ascii")
    t0 = time.monotonic()
    try:
        sock.sendto(data, (host, port))
        resp, addr = sock.recvfrom(256)
        latency_ms = (time.monotonic() - t0) * 1000
        return resp, latency_ms
    except socket.timeout:
        return None, TIMEOUT_SEC * 1000
    finally:
        sock.close()


def format_hex(data: bytes) -> str:
    return " ".join(f"{b:02x}" for b in data)


def run_test(host: str, port: int, repeat: int) -> dict[str, list]:
    results: dict[str, list] = {}
    print(f"\n{'='*60}")
    print(f"Relay poll test — {host}:{port}")
    print(f"Repeat: {repeat}x per payload | Timeout: {TIMEOUT_SEC}s")
    print(f"{'='*60}\n")

    for payload, label in PAYLOADS:
        print(f"[{payload}] {label}")
        replies = []
        latencies = []
        for i in range(repeat):
            resp, lat = send_poll(host, port, payload)
            replies.append(resp)
            latencies.append(lat)
            time.sleep(0.3)

            if resp is None:
                print(f"  run {i+1}: TIMEOUT")
            else:
                try:
                    text = resp.decode("ascii").strip()
                except UnicodeDecodeError:
                    text = f"<hex:{format_hex(resp)}>"
                print(f"  run {i+1}: reply={resp!r} ({text}) lat={lat:.1f}ms")

        results[payload] = {"label": label, "replies": replies, "latencies": latencies}
        print()

    return results


def summarize(results: dict) -> None:
    print(f"\n{'='*60}")
    print("SUMMARY TABLE")
    print(f"{'='*60}")
    print(f"{'Payload':<10} {'Reply pattern':<30} {'Avg lat (ms)':<12} {'Count'}")
    print("-" * 60)

    for payload, data in results.items():
        replies = data["replies"]
        latencies = data["latencies"]
        avg_lat = sum(latencies) / len(latencies) if latencies else 0
        count_ok = sum(1 for r in replies if r is not None)
        count_timeout = sum(1 for r in replies if r is None)

        if count_ok > 0:
            reply_samples = [r for r in replies if r is not None][:2]
            sample_strs = []
            for r in reply_samples:
                try:
                    t = r.decode("ascii").strip()
                    sample_strs.append(t)
                except UnicodeDecodeError:
                    sample_strs.append(f"hex:{format_hex(r)}")
            reply_str = ", ".join(sample_strs)
        else:
            reply_str = "TIMEOUT"

        print(f"{payload:<10} {reply_str:<30} {avg_lat:<12.1f} {count_ok}/{len(replies)}")

    print()


def detect_scenario(results: dict) -> str:
    """Heuristically detect which scenario we're in."""
    p0000_replies = [r for r in results.get("P0000", {}).get("replies", []) if r is not None]
    i0000_replies = [r for r in results.get("I0000", {}).get("replies", []) if r is not None]

    # Check P0000: expect P000000000 pulse echo
    p0000_ok = any(
        r is not None and len(r) == 10 and r.startswith(b"P")
        for r in p0000_replies
    )

    # Check I0000: expect I... status (I<CH><state> pattern)
    i0000_ok = any(
        r is not None and len(r) >= 7 and r.startswith(b"I")
        for r in i0000_replies
    )

    if p0000_ok and not i0000_ok:
        return "B"  # P0000 pulse only, no I<ch> status
    if i0000_ok:
        return "A"  # I<ch> gives status reply
    return "inconclusive"


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Relay poll test")
    parser.add_argument("--relay", default=RELAY_HOST_DEFAULT)
    parser.add_argument("--port", type=int, default=RELAY_PORT_DEFAULT)
    parser.add_argument("--repeat", type=int, default=REPEAT_DEFAULT)
    args = parser.parse_args()

    results = run_test(args.relay, args.port, args.repeat)
    summarize(results)

    scenario = detect_scenario(results)
    if scenario == "A":
        print("SCENARIO A: I<ch> poll gives status reply — recommend switch to I<ch> poll")
    elif scenario == "B":
        print("SCENARIO B: I<ch> poll gives no status reply — P0000 only confirmed")
    else:
        print("SCENARIO inconclusive — manual review needed")

    sys.exit(0)