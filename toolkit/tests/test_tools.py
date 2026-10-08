"""Tool behaviour against a fake gateway. No real network."""

from __future__ import annotations

import socket

import pytest

from ipbuilding_debug.errors import (
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_REMOTE_DEBUGGING_OFF,
    MSG_UNREACHABLE,
    NOT_AVAILABLE_PHRASE,
)
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import (
    capture_frames,
    connection_status,
    decode_test,
    export_session,
    probe_generation,
    send_raw,
)
from fake_gateway import FakeGateway


def _closed_port() -> int:
    sock = socket.socket()
    sock.bind(("127.0.0.1", 0))
    port = sock.getsockname()[1]
    sock.close()
    return port


@pytest.mark.asyncio
async def test_connection_status_unreachable() -> None:
    session = GatewaySession(
        f"127.0.0.1:{_closed_port()}",
        backoff_start=30,
        backoff_max=30,
    )
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
    assert result.message == MSG_UNREACHABLE
    assert result.data["kind"] == "unreachable"


@pytest.mark.asyncio
async def test_connection_status_switch_off_on_current_gateway() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == MSG_REMOTE_DEBUGGING_OFF
    assert result.data["remote_debugging"] is False
    assert result.data["capabilities"] == []
    assert result.data["ok"] is False


@pytest.mark.asyncio
async def test_connection_status_switch_on() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["udp_frame"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["ok"] is True
    assert result.data["remote_debugging"] is True
    assert "Remote debugging and control" in result.message
    assert NOT_AVAILABLE_PHRASE in result.message
    assert "log_stream" in result.data["missing_capabilities"]


@pytest.mark.asyncio
async def test_probe_lists_modules_without_the_switch() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await probe_generation(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["ok"] is True
    assert result.data["modules"][0]["model"] == "IP0200PoE"
    assert "PoE" in result.message
    assert MSG_REMOTE_DEBUGGING_OFF in result.message


@pytest.mark.asyncio
async def test_capture_frames_not_in_this_version() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await capture_frames(session, seconds=0.1)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["kind"] == "not_available"
    assert NOT_AVAILABLE_PHRASE in result.message
    assert gateway.received == []


@pytest.mark.asyncio
async def test_capture_frames_switch_off_when_feature_exists() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=["udp_frame"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await capture_frames(session, seconds=0.1)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == MSG_REMOTE_DEBUGGING_OFF
    assert gateway.received == []


@pytest.mark.asyncio
async def test_capture_frames_subscribes_and_returns_a_frame() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["udp_frame"])
    gateway.frame_on_subscribe = {
        "type": "udp_frame",
        "direction": "rx",
        "hex": "5330303030",
        "src": "module",
        "dst": "gateway",
        "port": 1001,
    }
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        await session.ensure_started()
        assert await session.wait_until_connected(3)
        # A frame from before this capture must stay outside the window.
        await session.buffer.append(
            {
                "type": "udp_frame",
                "direction": "rx",
                "hex": "00",
                "src": "old",
                "dst": "gateway",
                "port": 1001,
            }
        )
        result = await capture_frames(session, seconds=5, direction="rx", limit=1)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["ok"] is True
    assert len(result.data["frames"]) == 1
    assert result.data["frames"][0]["hex"] == "5330303030"
    assert result.data["frames"][0]["local_decode"]["matched"] is True
    assert any(item.get("type") == "subscribe_udp_frames" for item in gateway.received)


@pytest.mark.asyncio
async def test_log_level_rate_limit_is_explained() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    gateway.log_level_reply = {
        "type": "error",
        "error": "log_level_rate_limited",
        "message": "Too many log level changes. Wait and try again.",
    }
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session, log_level="debug")
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == MSG_LOG_LEVEL_RATE_LIMITED
    assert result.data["kind"] == "log_level_rate_limited"
    assert result.data["ok"] is False
    sent = [item for item in gateway.received if item.get("type") == "set_log_level"]
    assert sent
    assert sent[-1]["level"] == "DEBUG"
    assert sent[-1]["ttl"] == 900


@pytest.mark.asyncio
async def test_send_raw_preview_does_not_send() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            target="module-a",
            payload_hex="5330303030",
            confirmed=False,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["sent"] is False
    assert result.data["kind"] == "confirmation_required"
    assert "5330303030" in result.message
    assert gateway.raw_calls == []


@pytest.mark.asyncio
async def test_send_raw_not_available_does_not_post() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            target="module-a",
            payload_hex="53 30 30 30 30",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert NOT_AVAILABLE_PHRASE in result.message
    assert gateway.raw_calls == []


@pytest.mark.asyncio
async def test_send_raw_disabled_code_from_gateway() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    gateway.raw_status = 403
    gateway.raw_body = {"error": "remote_debugging_disabled", "message": "uit"}
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            target="module-a",
            payload_hex="5330303030",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == MSG_REMOTE_DEBUGGING_OFF
    assert result.data["sent"] is False
    assert len(gateway.raw_calls) == 1


@pytest.mark.asyncio
async def test_send_raw_confirmed_returns_replies() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            target="module-a",
            payload_hex="5330303030",
            port=1001,
            window_ms=2000,
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["sent"] is True
    assert gateway.raw_calls == [
        {
            "target": "module-a",
            "port": 1001,
            "payload_hex": "5330303030",
            "window_ms": 2000,
        }
    ]
    assert result.data["replies"][0]["local_decode"]["matched"] is True


def test_decode_test_matches_relay_and_reports_a_miss() -> None:
    matched = decode_test("S0000")
    assert matched.data["matched"] is True
    assert matched.data["matches"][0]["decoder"] == "relay"
    missed = decode_test("zzzz")
    assert missed.data["matched"] is False
    assert "Geen enkele decoder" in missed.message


@pytest.mark.asyncio
async def test_export_session_includes_note_and_gap() -> None:
    session = GatewaySession("127.0.0.1:9", backoff_start=30, backoff_max=30)
    await session.buffer.append(
        {
            "type": "gap",
            "from": "2026-01-01T00:00:00Z",
            "to": "2026-01-01T00:00:02Z",
            "message": "geen verbinding van 2026-01-01T00:00:00Z tot 2026-01-01T00:00:02Z",
        }
    )
    result = await export_session(session, note="lamp bleef aan", marker="hypothese-1")
    assert result.data["notes"][0]["text"] == "lamp bleef aan"
    assert result.data["notes"][0]["marker"] == "hypothese-1"
    assert result.data["gaps"]
    assert "ruimtes" in result.data["sharing"]
