"""Tests for gateway.udp_bus (simulated mode)."""

import asyncio

import pytest

from gateway.config import GatewayConfig
from gateway.udp_bus import UDPBus, UDPPacket


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


@pytest.mark.asyncio
async def test_polling_can_be_disabled_at_runtime():
    """The debug toggle must stop poll-loop traffic without restarting the bus."""
    cfg = GatewayConfig(simulated_mode=True, poll_interval_s=0.05)
    bus = UDPBus(cfg)

    sent_commands: list[tuple[str, bytes]] = []
    _original_send = bus.send_command

    async def _tracking_send(module_ip: str, payload: bytes, port: int | None = None) -> None:
        sent_commands.append((module_ip, payload))
        await _original_send(module_ip, payload, port)

    bus.send_command = _tracking_send  # type: ignore[assignment]
    await bus.start()
    assert bus.polling_enabled is True

    # Let the loop run a couple of rounds to confirm baseline activity.
    await asyncio.sleep(0.12)
    polls_before = [c for c in sent_commands if c[1] in (b"P0000", b"I9900", b"I0000")]
    assert polls_before, "expected poll-loop traffic before disabling"

    bus.set_polling_enabled(False)
    assert bus.polling_enabled is False

    # Reset the tracking list and verify no further poll-loop traffic flows.
    sent_commands.clear()
    await asyncio.sleep(0.12)
    polls_after = [c for c in sent_commands if c[1] in (b"P0000", b"I9900", b"I0000")]
    assert polls_after == [], "polling must stop while disabled"

    # Re-enabling must resume polling without a bus restart.
    bus.set_polling_enabled(True)
    assert bus.polling_enabled is True
    await asyncio.sleep(0.12)
    polls_resumed = [c for c in sent_commands if c[1] in (b"P0000", b"I9900", b"I0000")]
    assert polls_resumed, "polling must resume when re-enabled"

    await bus.stop()
