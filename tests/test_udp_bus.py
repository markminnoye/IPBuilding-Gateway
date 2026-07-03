"""Tests for gateway.udp_bus (simulated mode)."""

import asyncio
import time

import pytest

from gateway.config import GatewayConfig
from gateway.udp_bus import UDPBus, UDPPacket, _RECENT_PACKETS_MAX


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


@pytest.mark.asyncio
async def test_listener_receives_simulated_reply():
    cfg = GatewayConfig(simulated_mode=True)
    bus = UDPBus(cfg)

    received: list[UDPPacket] = []
    bus.add_listener(received.append)

    bus.register_simulated_reply(b"P0000", b"P000000000")
    await bus.start()

    await bus.send_command("10.10.1.30", b"P0000")
    assert len(received) == 1
    assert received[0].data == b"P000000000"
    assert received[0].src_ip == "10.10.1.30"

    await bus.stop()


@pytest.mark.asyncio
async def test_remove_listener():
    cfg = GatewayConfig(simulated_mode=True)
    bus = UDPBus(cfg)

    received: list[UDPPacket] = []
    bus.add_listener(received.append)
    bus.register_simulated_reply(b"P0000", b"P000000000")
    await bus.start()

    await bus.send_command("10.10.1.30", b"P0000")
    assert len(received) == 1

    bus.remove_listener(received.append)
    await bus.send_command("10.10.1.30", b"P0000")
    assert len(received) == 1

    await bus.stop()


@pytest.mark.asyncio
async def test_poll_loop_sends_to_all_modules():
    """Poll loop should send poll payloads to all configured modules."""
    cfg = GatewayConfig(simulated_mode=True, poll_interval_s=0.05)
    bus = UDPBus(cfg)

    sent_commands: list[tuple[str, bytes]] = []
    _original_send = bus.send_command

    async def _tracking_send(module_ip: str, payload: bytes, port: int | None = None) -> None:
        sent_commands.append((module_ip, payload))
        await _original_send(module_ip, payload, port)

    bus.send_command = _tracking_send  # type: ignore[assignment]
    await bus.start()

    await asyncio.sleep(0.15)
    await bus.stop()

    relay_polls = [(ip, p) for ip, p in sent_commands if p == b"P0000"]
    dimmer_polls = [(ip, p) for ip, p in sent_commands if p == b"I9900"]
    input_polls = [(ip, p) for ip, p in sent_commands if p == b"I0000"]

    assert len(relay_polls) >= 1, "Relay should have been polled"
    assert len(dimmer_polls) >= 1, "Dimmer should have been polled"
    assert len(input_polls) >= 1, "Input should have been polled"

    assert relay_polls[0][0] == "10.10.1.30"
    assert dimmer_polls[0][0] == "10.10.1.40"
    assert input_polls[0][0] == "10.10.1.50"


@pytest.mark.asyncio
async def test_poll_loop_stops_cleanly():
    """Poll loop task should cancel without error on stop()."""
    cfg = GatewayConfig(simulated_mode=True, poll_interval_s=0.05)
    bus = UDPBus(cfg)
    await bus.start()

    assert bus._poll_task is not None
    assert not bus._poll_task.done()

    await bus.stop()

    assert bus._poll_task is None


@pytest.mark.asyncio
async def test_poll_replies_do_not_accumulate_unbounded_queue():
    """Regression: poll replies must not pile up in an internal queue."""
    cfg = GatewayConfig(simulated_mode=True, poll_interval_s=0.05)
    bus = UDPBus(cfg)

    received: list[UDPPacket] = []
    bus.add_listener(received.append)
    bus.register_simulated_reply(b"P0000", b"P000000000")
    bus.register_simulated_reply(b"I9900", b"I0154099")
    bus.register_simulated_reply(b"I0000", b"I000000000")

    await bus.start()
    await asyncio.sleep(0.2)
    await bus.stop()

    assert len(received) >= 3
    assert not hasattr(bus, "_queue")
    assert len(bus._recent_packets) <= _RECENT_PACKETS_MAX


@pytest.mark.asyncio
async def test_correlate_reply_works_during_active_polling():
    """correlate_reply must still work while the poll loop is running."""
    cfg = GatewayConfig(simulated_mode=True, poll_interval_s=0.05)
    bus = UDPBus(cfg)
    bus.register_simulated_reply(b"P0000", b"P000000000")
    bus.register_simulated_reply(b"mJS0000", b"I00000100")

    await bus.start()
    await asyncio.sleep(0.1)

    ts = time.monotonic()
    await bus.send_command("10.10.1.30", b"mJS0000")
    pkt = await bus.correlate_reply(
        module_ip="10.10.1.30",
        after_ts=ts,
        timeout_ms=500,
        predicate=lambda data: data.startswith(b"I"),
    )
    assert pkt is not None
    assert pkt.data == b"I00000100"

    await bus.stop()


@pytest.mark.asyncio
async def test_listener_exception_does_not_crash_bus():
    """A broken listener should not prevent other listeners from receiving."""
    cfg = GatewayConfig(simulated_mode=True)
    bus = UDPBus(cfg)

    received: list[UDPPacket] = []

    def bad_listener(pkt: UDPPacket) -> None:
        raise ValueError("boom")

    bus.add_listener(bad_listener)
    bus.add_listener(received.append)
    bus.register_simulated_reply(b"P0000", b"P000000000")

    await bus.start()
    await bus.send_command("10.10.1.30", b"P0000")

    assert len(received) == 1
    await bus.stop()
