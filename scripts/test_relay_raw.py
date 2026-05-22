#!/usr/bin/env python3
"""Direct relay control via UDP/1001 — without IPBox."""

import socket
import sys

RELAY_HOST = "10.10.1.30"
RELAY_PORT = 1001

def send_command(payload: str) -> None:
    """Send ASCII command to relay module."""
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    data = payload.encode("ascii")
    print(f"Sending: {payload!r} ({len(data)} bytes) → {RELAY_HOST}:{RELAY_PORT}")
    sock.sendto(data, (RELAY_HOST, RELAY_PORT))
    sock.settimeout(2.0)
    try:
        resp, addr = sock.recvfrom(1024)
        print(f"Response: {resp!r} from {addr}")
    except socket.timeout:
        print("No response (timeout)")
    sock.close()

def main():
    if len(sys.argv) != 3:
        print("Usage: python3 test_relay_raw.py <S|C|P> <channel>")
        print("Example: python3 test_relay_raw.py S 14   # Aanzetten kanaal 14")
        print("         python3 test_relay_raw.py C 14   # Uitzetten kanaal 14")
        sys.exit(1)

    action = sys.argv[1].upper()
    channel = int(sys.argv[2])
    ch = f"{channel:02d}"
    cmd = f"{action}{ch}00"
    send_command(cmd)

if __name__ == "__main__":
    main()