"""Tests for gateway.udp_bus (simulated mode)."""

import asyncio

import pytest

from gateway.config import GatewayConfig
from gateway.udp_bus import UDPBus


@pytest.mark.asyncio
async def test_simulated_reply_correlation():
    cfg = GatewayConfig(simulated_mode=True)
    bus = UDPBus(cfg)
    await bus.start()

    cmd = b"mJS0000"
    reply = b"I00000100"
    bus.register_simulated_reply(cmd, reply)

    ts = asyncio.get_event_loop().time()
    await bus.send_command("10.10.1.30", cmd)
    pkt = await bus.correlate_reply(
        module_ip="10.10.1.30",
        after_ts=ts - 1,
        timeout_ms=200,
    )
    assert pkt is not None
    assert pkt.data == reply
    await bus.stop()
