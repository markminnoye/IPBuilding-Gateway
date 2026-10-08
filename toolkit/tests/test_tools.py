"""Tool behaviour against a fake gateway. No real network."""

from __future__ import annotations

import socket

import pytest

from ipbuilding_debug.errors import (
    MSG_GATEWAY_TOO_OLD,
    MSG_LOG_LEVEL_RATE_LIMITED,
    MSG_REMOTE_DEBUGGING_OFF,
    MSG_UNREACHABLE,
    NOT_AVAILABLE_PHRASE,
)
from ipbuilding_debug.session import GatewaySession
from ipbuilding_debug.tools import (
    CHANNEL_NUMBERING,
    COMMAND_WARNING,
    capture_frames,
    connection_status,
    decode_test,
    device_command,
    discover,
    export_session,
    gateway_health,
    list_devices,
    probe_generation,
    recent_events,
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
    assert result.data["redacted"] is True
    assert "adressen" in result.data["sharing"]


def _dotted(*parts: int) -> str:
    return ".".join(str(part) for part in parts)


def _mac() -> str:
    return ":".join(["ab"] * 6)


@pytest.mark.asyncio
async def test_old_gateway_is_connected_with_missing_capabilities() -> None:
    gateway = FakeGateway()
    gateway.omit_toolkit_fields = True
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["connected"] is True
    assert result.data["ok"] is True
    assert result.data["missing_capabilities"] == ["log_stream", "udp_frame", "raw_send"]
    assert "te oud voor live debugging" in result.message
    assert "develop-kanaal" in result.message
    assert result.message == MSG_GATEWAY_TOO_OLD
    assert result.data["address_source"] == "manual"
    assert result.data["port"] == gateway.port
    assert result.data["health"]["status"] == "ok"
    assert result.data["health"]["uptime_seconds"] == 12


@pytest.mark.asyncio
async def test_gateway_health_reads_status_fields() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])

    def status_body() -> dict:
        body = FakeGateway.status_body(gateway)
        body["issues"] = [
            {
                "id": "installation.missing",
                "level": "error",
                "code": "installation.missing",
                "message": "geen installatie",
            }
        ]
        return body

    gateway.status_body = status_body  # type: ignore[method-assign]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await gateway_health(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["health"]["subsystems"]["discovery"] == "ok"
    assert result.data["health"]["issues"][0]["code"] == "installation.missing"
    assert "buffer" in result.data


@pytest.mark.asyncio
async def test_list_devices_maps_channels_from_zero_and_last_seen() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    gateway.modules = [
        {
            "id": "module-a",
            "type": "relay",
            "model": "IP0200PoE",
            "firmware": "1",
            "name": "relay-a",
            "last_seen": "2026-01-01T00:00:00+00:00",
            "last_seen_source": "udp",
        },
        {
            "id": "module-c",
            "type": "input",
            "model": "IP1100PoE",
            "name": "input-c",
        },
    ]
    gateway.devices = [
        {
            "id": "device-a",
            "module_id": "module-a",
            "channel": 0,
            "name": "lamp-a",
            "room": "room-a",
            "device_type": "relay",
            "state": "off",
            "active": True,
        },
        {
            "id": "button-a",
            "module_id": "module-c",
            "channel": 1,
            "name": "button-a",
            "device_type": "input",
            "semantic_type": "button",
            "active": True,
        },
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await list_devices(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["channel_numbering"] == CHANNEL_NUMBERING
    assert "vanaf 0" in result.message
    relay = result.data["devices"][0]
    assert relay["channel"] == 0
    assert relay["device_type"] == "relay"
    assert relay["state"] == "off"
    assert relay["last_seen_source"] == "udp"
    button = result.data["devices"][1]
    assert button["state"] is None
    assert "geen status" in button["state_note"]
    unseen = result.data["modules"][1]
    assert unseen["last_seen"] is None
    assert "last_seen" in unseen["last_seen_note"]


@pytest.mark.asyncio
async def test_recent_events_reads_buffer_without_frames() -> None:
    session = GatewaySession("localhost:9", backoff_start=30, backoff_max=30)
    await session.buffer.append(
        {"type": "state_changed", "id": "device-a", "state": "on"}
    )
    await session.buffer.append(
        {"type": "button_event", "id": "button-a", "action": "single_press"}
    )
    await session.buffer.append({"type": "udp_frame", "hex": "00"})
    result = await recent_events(session)
    kinds = [event["type"] for event in result.data["events"]]
    assert kinds == ["state_changed", "button_event"]
    assert result.data["events"][1]["action"] == "single_press"


@pytest.mark.asyncio
async def test_discover_waits_for_confirmation_then_diffs() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        preview = await discover(session, confirmed=False)
        assert preview.data["sent"] is False
        assert gateway.discover_calls == []
        done = await discover(session, confirmed=True)
    finally:
        await session.stop()
        await gateway.stop()
    assert done.data["sent"] is True
    assert done.data["diff"]["modules_added"] == ["module-b"]
    assert "device-b" in done.data["diff"]["devices_added"]
    assert done.data["gateway"]["added"] == [{"mac": "module-b"}]
    assert len(gateway.discover_calls) == 1


@pytest.mark.asyncio
async def test_device_command_previews_then_warns_ok_is_not_a_reply() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        preview = await device_command(
            session, device_id="device-a", action="on", confirmed=False
        )
        assert preview.data["sent"] is False
        assert gateway.command_calls == []
        assert "confirmed=true" in preview.message
        missing = await device_command(
            session, device_id="device-a", action="DIM", confirmed=True
        )
        assert missing.data["sent"] is False
        sent = await device_command(
            session, device_id="device-a", action="off", confirmed=True
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert sent.data["sent"] is True
    assert sent.data["ok"] is True
    assert COMMAND_WARNING in sent.message
    assert "ook als de module niet antwoordt" in sent.message
    assert gateway.command_calls == [
        {"device_id": "device-a", "action": "OFF"}
    ]


@pytest.mark.asyncio
async def test_export_redacts_by_default_and_can_show_raw_locally() -> None:
    host = _dotted(198, 51, 100, 24)
    mac = _mac()
    session = GatewaySession("localhost:9", backoff_start=30, backoff_max=30)
    await session.buffer.append(
        {
            "type": "state_changed",
            "id": "device-a",
            "name": "lamp-a",
            "room": "room-a",
            "module_ip": host,
            "mac": mac,
            "state": "on",
        }
    )
    hidden = await export_session(session, note=f"zag {host} in room-a")
    blob = hidden.render()
    assert hidden.data["redacted"] is True
    assert host not in blob
    assert mac not in blob
    assert "lamp-a" not in blob
    assert "room-a" not in blob
    assert "device-a" not in blob
    raw = await export_session(session, redact=False)
    raw_blob = raw.render()
    assert raw.data["redacted"] is False
    assert host in raw_blob
    assert "lamp-a" in raw_blob
    assert "Deel deze tekst niet" in raw.message
