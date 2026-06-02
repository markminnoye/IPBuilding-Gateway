"""UDP/10001 discovery spike — listen for module replies to probe 0x01000000.

RE methodology
--------------
Phase 1 (passive): listen while IPBox sends probes; observe whether module
                   replies are visible from this host/POV.
Phase 2 (active):  send probe yourself (requires gateway on 10.10.1.1);
                   observe whether modules reply.

Based on prior RE (RE_STATE.md, 2026-05-17): IPBox broadcasts ``01 00 00 00``
on UDP/10001 to ``255.255.255.255`` and ``233.89.188.1`` ~every 10.5 s.
No module replies were observed on mirror 7←15 — this spike determines
whether a different POV or host binding changes that.

Usage
-----
    # Phase 1 — passive (IPBox running)
    sudo python scripts/udp10001_listen.py --duration 60

    # Phase 2 — active (IPBox off, gateway on 10.10.1.1)
    sudo python scripts/udp10001_listen.py --send-probe --duration 60

    # Alternative: tshark capture
    sudo tshark -i en7 -f 'udp port 10001' \\
      -T fields -e frame.time_relative -e ip.src -e ip.dst -e udp.payload \\
      | tee /tmp/udp10001_spike.txt

Go/no-go for Task 3 (gateway/discovery.py)
-------------------------------------------
- Replies seen (any scenario)  → GO-A: UDP probe primary in gateway CLI
- No replies in both scenarios → GO-B: HTTP sweep primary (always works)

Note: sudo may be required to bind UDP port 10001 on macOS.
"""
from __future__ import annotations

import argparse
import asyncio
import datetime
import socket
import sys

LISTEN_PORT = 10001
PROBE_PAYLOAD = b"\x01\x00\x00\x00"
BROADCAST_TARGETS = ["255.255.255.255", "233.89.188.1"]

# Known MACs from RE — used to correlate replies with module identities
KNOWN_MACS: dict[str, str] = {
    "00:24:77:52:ac:be": "relay  10.10.1.30 (IP200PoE)",
    "00:24:77:52:9e:a8": "dimmer 10.10.1.40 (IP0300PoE)",
    "00:24:77:52:ad:aa": "input  10.10.1.50 (IP1100PoE)",
}


def _try_correlate_mac(payload: bytes) -> str:
    """Best-effort: if payload contains a known MAC substring, label it."""
    for mac_hex, label in KNOWN_MACS.items():
        mac_bytes = bytes.fromhex(mac_hex.replace(":", ""))
        if mac_bytes in payload:
            return f"  → correlates with {label}"
    return ""


async def listen(duration: int, send_probe: bool) -> None:
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
    sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
    sock.bind(("0.0.0.0", LISTEN_PORT))
    sock.setblocking(False)

    loop = asyncio.get_running_loop()

    if send_probe:
        for target in BROADCAST_TARGETS:
            sock.sendto(PROBE_PAYLOAD, (target, LISTEN_PORT))
        print(f"Sent probe {PROBE_PAYLOAD.hex()} to {BROADCAST_TARGETS}")

    print(f"Listening on UDP/{LISTEN_PORT} for {duration}s...")
    print("(filter: own probe echoed back is suppressed)")

    start = loop.time()
    packets: list[tuple[str, bytes]] = []

    while loop.time() - start < duration:
        try:
            data, addr = await loop.run_in_executor(None, lambda: sock.recvfrom(256))
            if data == PROBE_PAYLOAD:
                continue  # own probe echoed back — skip
            ts = datetime.datetime.now().isoformat(timespec="milliseconds")
            correlation = _try_correlate_mac(data)
            print(f"[{ts}] {addr[0]}:{addr[1]} → {data.hex()}  ({data!r}){correlation}")
            packets.append((addr[0], data))
        except BlockingIOError:
            await asyncio.sleep(0.05)

    sock.close()

    print(f"\n{'='*60}")
    print(f"Summary: {len(packets)} packet(s) received from field modules")
    print(f"{'='*60}")

    if not packets:
        print("VERDICT: GO-B — No UDP/10001 replies from this host/POV.")
        print("Gateway CLI will use HTTP-sweep as primary discovery path.")
        print("(UDP probe path still built but not primary)")
    else:
        print("VERDICT: GO-A — UDP/10001 replies observed.")
        print("Gateway CLI can use UDP probe as primary discovery path.")
        print()
        seen_ips: set[str] = set()
        for src, payload in packets:
            if src not in seen_ips:
                seen_ips.add(src)
                correlation = _try_correlate_mac(payload)
                print(f"  {src}: {payload.hex()}{correlation}")

    print()
    print("Document the verdict in:")
    print("  resources_and_docs/evidence/2026-06-XX_udp10001_discovery_spike.md")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="UDP/10001 discovery spike — listen for field module replies"
    )
    parser.add_argument(
        "--send-probe",
        action="store_true",
        help="Send 01000000 probe broadcast before listening (Phase 2 / active)",
    )
    parser.add_argument(
        "--duration",
        type=int,
        default=30,
        help="Listen duration in seconds (default: 30)",
    )
    args = parser.parse_args()

    try:
        asyncio.run(listen(args.duration, args.send_probe))
    except PermissionError:
        print("ERROR: binding UDP port 10001 requires elevated privileges.")
        print("Try: sudo python scripts/udp10001_listen.py ...")
        sys.exit(1)
    except OSError as exc:
        print(f"ERROR: {exc}")
        sys.exit(1)


if __name__ == "__main__":
    main()
