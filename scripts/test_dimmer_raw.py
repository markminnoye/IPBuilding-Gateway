#!/usr/bin/env python3
"""Test dimmer command with raw socket (bypassing asyncio)."""

import socket
import sys
import time

# Add gateway to path
sys.path.insert(0, "/Users/markminnoye/git/IPBuilding Gateway")

from gateway.payloads.dimmer import encode_dim_command
from gateway.models import DimmerCommand

def main():
    dimmer_ip = "10.10.1.40"
    dimmer_port = 1001
    local_ip = "10.10.1.100"

    cmd = DimmerCommand(channel=0, level=100)
    payload = encode_dim_command(cmd)
    print(f"Payload: {payload!r} (hex: {payload.hex()})")

    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    sock.settimeout(5.0)

    try:
        print(f"Binding to {local_ip}...")
        sock.bind((local_ip, 0))
        print(f"Sending to {dimmer_ip}:{dimmer_port} ...")
        sent_bytes = sock.sendto(payload, (dimmer_ip, dimmer_port))
        print(f"Sent {sent_bytes} bytes")

        print("Waiting for reply...")
        data, addr = sock.recvfrom(4096)
        print(f"Reply: {data.hex()} | {data!r} | ascii: {data.decode('ascii','replace')!r}")
        print(f"From: {addr}")
    except socket.timeout:
        print("Timeout after 5s — no reply")
    finally:
        sock.close()

if __name__ == "__main__":
    main()