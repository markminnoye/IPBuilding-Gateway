"""Ring buffer, reconnect, resubscribe, and the 30 second wait cap."""

from __future__ import annotations

import asyncio
import socket
import sys

import pytest

from ipbuilding_debug.buffer import RingBuffer, clamp_timeout
from ipbuilding_debug.session import GatewaySession, next_backoff
from fake_gateway import FakeGateway


def test_backoff_grows_from_one_second_to_thirty() -> None:
    delay = 1.0
    seen = []
    for _ in range(8):
        seen.append(delay)
        delay = next_backoff(delay, 30.0)
    assert seen == [1.0, 2.0, 4.0, 8.0, 16.0, 30.0, 30.0, 30.0]


def test_wait_is_capped_at_thirty_seconds() -> None:
    assert clamp_timeout(120) == 30
    assert clamp_timeout(5) == 5
    assert clamp_timeout(-1) == 0


@pytest.mark.asyncio
async def test_ring_buffer_drops_oldest_and_wait_for_state() -> None:
    buffer = RingBuffer(maxlen=3)
    for name in ("a", "b", "c", "d"):
        await buffer.append({"type": "state_changed", "id": name, "state": "on"})
    assert len(buffer) == 3
    assert buffer.dropped == 1
    ids = [item.event["id"] for item in buffer.since(0)]
    assert ids == ["b", "c", "d"]

    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    session.buffer = buffer

    async def push() -> None:
        await asyncio.sleep(0.05)
        await session.buffer.append(
            {"type": "state_changed", "id": "lamp", "state": "off"}
        )

    task = asyncio.create_task(push())
    found = await session.wait_for_state("lamp", timeout=120, state="off")
    await task
    assert found is not None
    assert found["state"] == "off"

    missing = await session.wait_for_state("nope", timeout=0.05)
    assert missing is None


@pytest.mark.asyncio
async def test_wait_for_state_passes_the_capped_timeout() -> None:
    session = GatewaySession("127.0.0.1:9")
    seen: dict[str, float] = {}

    async def spy(_predicate, timeout, _since):
        seen["timeout"] = timeout
        return None

    session.buffer.wait_until = spy  # type: ignore[method-assign]
    await session.wait_for_state("lamp", timeout=120)
    assert seen["timeout"] == 30


@pytest.mark.asyncio
async def test_reconnect_inserts_a_gap_resubscribes_and_resyncs() -> None:
    gateway = FakeGateway(
        remote_debugging=True,
        capabilities=["log_stream", "udp_frame"],
        drop_first=True,
    )
    await gateway.start()
    written: list[str] = []

    def _write(text: str) -> int:
        written.append(text)
        raise AssertionError(f"stdout write: {text!r}")

    previous = sys.stdout
    sys.stdout.write = _write  # type: ignore[method-assign]
    session = GatewaySession(
        f"127.0.0.1:{gateway.port}",
        backoff_start=0.05,
        backoff_max=0.2,
    )
    session.want_frames = True
    try:
        await session.ensure_started()
        for _ in range(100):
            subscribed = any(
                item.get("type") == "subscribe_logs" for item in gateway.received
            )
            frames = any(
                item.get("type") == "subscribe_udp_frames" for item in gateway.received
            )
            if (
                gateway.connects >= 2
                and "channel-b" in session.devices
                and "channel-a" not in session.devices
                and session.gap_events()
                and subscribed
                and frames
            ):
                break
            await asyncio.sleep(0.02)
        else:
            raise AssertionError(
                f"connects={gateway.connects} devices={list(session.devices)} "
                f"gaps={session.gap_events()} received={gateway.received}"
            )
        gap = session.gap_events()[0]
        assert gap["message"].startswith("geen verbinding van ")
        assert "tot " in gap["message"]
        assert written == []
    finally:
        sys.stdout.write = previous.write  # type: ignore[method-assign]
        await session.stop()
        await gateway.stop()


@pytest.mark.asyncio
async def test_failed_connect_uses_backoff_without_a_gap() -> None:
    sleeps: list[float] = []
    holder: dict[str, GatewaySession] = {}

    async def sleeper(seconds: float) -> None:
        sleeps.append(seconds)
        if len(sleeps) >= 3:
            holder["session"]._stopped.set()

    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    session = GatewaySession(
        f"127.0.0.1:{port}",
        backoff_start=1,
        backoff_max=30,
        sleeper=sleeper,
    )
    holder["session"] = session
    await session.ensure_started()
    for _ in range(50):
        if len(sleeps) >= 3:
            break
        await asyncio.sleep(0.02)
    await session.stop()
    assert sleeps[:3] == [1, 2, 4]
    assert session.gap_events() == []
