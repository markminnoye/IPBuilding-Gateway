#!/usr/bin/env python3
"""Relay poll payload test — I<CH>00 status read vs P0000 keepalive.

Tests whether relay module responds to on-demand status polls ``I<CH>00``
with per-channel status ``I000<CH><state>``, or only to ``P0000`` with
pulse echo.  Correct format (RE 2026-06-12): channel in the **first** two
digits after ``I``, e.g. ``I1800`` for channel 18 — not ``I0018``.

Run:
    python3 scripts/test_relay_poll.py [--relay HOST] [--port PORT] [--repeat N]

No args: uses 10.10.1.30:1001, repeat=3.
"""

import argparse
import socket
import sys
import time

RELAY_HOST_DEFAULT = "10.10.1.30"
RELAY_PORT_DEFAULT = 1001
REPEAT_DEFAULT = 3
TIMEOUT_SEC = 2.0

PAYLOADS = [
    ("P0000", "baseline pulse keepalive ch 0"),
    ("I0000", "status poll channel 0"),
    ("I1000", "status poll channel 10"),
    ("I1600", "status poll channel 16"),
    ("I1800", "status poll channel 18"),
    ("I2300", "status poll channel 23"),
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


def _is_relay_status_reply(data: bytes) -> bool:
    """True when reply looks like I000<CH><state> (10-byte status line)."""
    if len(data) != 10 or not data.startswith(b"I"):
        return False
    try:
        text = data.decode("ascii")
    except UnicodeDecodeError:
        return False
    return text[1:4] == "000" and text[4:6].isdigit() and text[6:].isdigit()


def detect_scenario(results: dict) -> str:
    """Heuristically detect which scenario we're in."""
    p0000_replies = [r for r in results.get("P0000", {}).get("replies", []) if r is not None]
    status_poll_keys = [k for k in results if k.startswith("I") and k != "I0000" or k == "I0000"]
    status_replies = []
    for key in status_poll_keys:
        status_replies.extend(
            r for r in results.get(key, {}).get("replies", []) if r is not None
        )

    p0000_ok = any(
        r is not None and len(r) == 10 and r.startswith(b"P")
        for r in p0000_replies
    )

    status_ok = any(_is_relay_status_reply(r) for r in status_replies)

    if p0000_ok and status_ok:
        return "A"  # I<CH>00 gives per-channel status; P0000 keepalive
    if p0000_ok and not status_ok:
        return "B"  # P0000 pulse only, no I<CH>00 status
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
        print(
            "SCENARIO A: I<CH>00 status poll works — use startup sweep "
            "(gateway.state_poll.sweep_relay_states)"
        )
    elif scenario == "B":
        print("SCENARIO B: I<CH>00 gives no status reply — P0000 only confirmed")
    else:
        print("SCENARIO inconclusive — manual review needed")

    sys.exit(0)
