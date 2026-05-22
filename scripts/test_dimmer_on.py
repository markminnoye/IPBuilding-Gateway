#!/usr/bin/env python3
"""Test dimmer command — longer wait + raw print."""

import asyncio
import sys
import os
import time

sys.path.insert(0, os.path.dirname(__file__))

from gateway.payloads.dimmer import encode_dim_command
from gateway.models import DimmerCommand
from gateway.udp_bus import UDPBus, UDPPacket
from gateway.config import GatewayConfig

async def main():
    cfg = GatewayConfig.from_env()
    cfg.bind_ip = "10.10.1.100"
    print(f"bind={cfg.bind_ip}, dimmer={cfg.field_modules['dimmer']}, hub={cfg.hub_ip}")

    bus = UDPBus(cfg)
    await bus.start()

    cmd = DimmerCommand(channel=0, level=100)
    payload = encode_dim_command(cmd)
    dimmer_ip = cfg.field_modules["dimmer"]
    print(f"Sending: {payload!r} -> {dimmer_ip}:1001")

    sent_ts = time.monotonic()
    await bus.send_command(dimmer_ip, payload, port=1001)
    print("Waiting 5s for any UDP reply from dimmer...")

    reply = await bus.correlate_reply(
        module_ip=dimmer_ip,
        after_ts=sent_ts,
        timeout_ms=5000,
    )

    if reply:
        print(f"Got reply at +{reply.monotonic_ts - sent_ts:.3f}s")
        print(f"  raw hex: {reply.data.hex()}")
        print(f"  raw bytes: {reply.data!r}")
        # Try to decode as ASCII
        try:
            print(f"  ascii: {reply.data.decode('ascii')!r}")
        except Exception as e:
            print(f"  ascii decode error: {e}")
    else:
        print("No reply after 5s")

    await bus.stop()

if __name__ == "__main__":
    asyncio.run(main())