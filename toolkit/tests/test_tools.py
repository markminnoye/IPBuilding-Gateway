"""Tool behaviour against a fake gateway. No real network."""

from __future__ import annotations

import re
import socket
from datetime import datetime, timezone

import pytest

from ipbuilding_debug.dialect import legacy_segments
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
    read_logs,
    recent_events,
    send_raw,
    unavailable_tools,
    _feature_rows,
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
    assert "Remote control (for debugging)" in result.message
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


_MODULE = "192.0.2.10"


@pytest.mark.asyncio
async def test_send_raw_preview_does_not_send() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            module_ip=_MODULE,
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
            module_ip=_MODULE,
            payload_hex="53 30 30 30 30",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert "niet ondersteund in deze gatewayversie" in result.message
    assert gateway.raw_calls == []


@pytest.mark.asyncio
async def test_send_raw_switch_off_does_not_post() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="5330303030",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == (
        'Zet in de gateway "Bediening op afstand (voor debuggen)" aan.'
    )
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
            module_ip=_MODULE,
            payload_hex="5330303030",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == (
        'Zet in de gateway "Bediening op afstand (voor debuggen)" aan.'
    )
    assert result.data["sent"] is False
    assert len(gateway.raw_calls) == 1


@pytest.mark.asyncio
@pytest.mark.parametrize(
    ("status", "code"),
    [
        (422, "target_not_allowed"),
        (422, "invalid_target"),
        (429, "raw_send_rate_limited"),
        (429, "raw_send_busy"),
        (503, "send_failed"),
        (400, "invalid_payload"),
        (400, "invalid_window"),
    ],
)
async def test_send_raw_surfaces_gateway_errors(status: int, code: str) -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    gateway.raw_status = status
    gateway.raw_body = {"error": code, "message": "english"}
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="5330303030",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["ok"] is False
    assert result.data["kind"] == code
    assert result.message
    assert "english" not in result.message
    assert code not in result.message


@pytest.mark.asyncio
async def test_send_raw_confirmed_returns_replies() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="5330303030",
            port=1001,
            window_ms=2000,
            confirmed=True,
        )
        gateway.replies = []
        gateway.raw_truncated = True
        empty = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="5330303030",
            confirmed=True,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["sent"] is True
    assert result.data["ok"] is True
    assert gateway.raw_calls[0] == {
        "module_ip": _MODULE,
        "port": 1001,
        "payload_hex": "5330303030",
        "window_ms": 2000,
    }
    assert result.data["sent_hex"] == "5330303030"
    assert result.data["window_ms"] == 2000
    assert result.data["truncated"] is False
    assert result.data["replies"][0]["delay_ms"] == 40
    assert result.data["replies"][0]["local_decode"]["matched"] is True
    assert empty.data["ok"] is True
    assert empty.data["replies"] == []
    assert empty.data["truncated"] is True
    assert "gelukt" in empty.message
    assert "hoogstens 8" in empty.message


@pytest.mark.asyncio
async def test_send_raw_rejects_a_bad_window_and_a_long_payload() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["raw_send"])
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        window = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="5330303030",
            window_ms=3001,
            confirmed=True,
        )
        payload = await send_raw(
            session,
            module_ip=_MODULE,
            payload_hex="aa" * 65,
            confirmed=False,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert window.data["kind"] == "invalid_window"
    assert "3000" in window.message
    assert payload.data["kind"] == "invalid_payload"
    assert gateway.raw_calls == []


@pytest.mark.asyncio
async def test_decode_test_matches_relay_and_reports_a_miss() -> None:
    matched = await decode_test("S0000")
    assert matched.data["matched"] is True
    assert matched.data["matches"][0]["decoder"] == "relay"
    missed = await decode_test("zzzz")
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
    assert "adressen" in result.data["sharing"].lower()


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
    assert "te oud voor live debugging" in result.message
    assert "send_raw" in result.message
    assert "raw_send" in result.message
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
async def test_list_devices_keeps_input_channel_31() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    gateway.modules = [
        {"id": "module-c", "type": "input", "model": "IP1100PoE", "name": "input-c"}
    ]
    gateway.devices = [
        {
            "id": f"button-{channel}",
            "module_id": "module-c",
            "channel": channel,
            "name": f"button-{channel}",
            "device_type": "input",
            "active": channel != 31,
        }
        for channel in (0, 30, 31, 32)
    ]
    await gateway.start()
    session = GatewaySession(f"127.0.0.1:{gateway.port}", backoff_start=0.05)
    try:
        result = await list_devices(session)
    finally:
        await session.stop()
        await gateway.stop()
    channels = [row["channel"] for row in result.data["devices"]]
    assert channels == [0, 30, 31, 32]
    assert "kanaal 31" in result.message
    assert sum(1 for row in result.data["devices"] if row["channel"] == 31) == 1


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
    assert sent.data["confirmation_available"] is False
    assert sent.data["module_confirmed"] is None
    assert COMMAND_WARNING in sent.message
    assert "niet beschikbaar in deze gatewayversie" in sent.message
    assert gateway.command_calls == [
        {"device_id": "device-a", "action": "OFF"}
    ]


@pytest.mark.asyncio
async def test_device_command_reports_module_confirmation_when_present() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    gateway.command_body = {
        "ok": True,
        "schema_version": 2,
        "module_confirmed": True,
        "confirm_ms": 42,
        "reported": {"state": "on"},
    }
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        sent = await device_command(
            session, device_id="device-a", action="ON", confirmed=True
        )
        gateway.command_body = {
            "ok": True,
            "module_confirmed": False,
            "confirm_ms": None,
            "reported": None,
        }
        missed = await device_command(
            session, device_id="device-a", action="OFF", confirmed=True
        )
        gateway.command_body = {
            "ok": True,
            "module_confirmed": False,
            "confirm_ms": None,
            "reported": None,
        }
        started = await device_command(
            session, device_id="device-a", action="DIM_START", confirmed=True
        )
        gateway.command_body = {
            "ok": True,
            "module_confirmed": "yes",
            "confirm_ms": True,
            "reported": "on",
        }
        odd = await device_command(
            session, device_id="device-a", action="ON", confirmed=True
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert sent.data["confirmation_available"] is True
    assert sent.data["module_confirmed"] is True
    assert sent.data["confirm_ms"] == 42
    assert sent.data["reported"] == {"state": "on"}
    assert "42 ms" in sent.message
    assert "status on" in sent.message
    assert missed.data["module_confirmed"] is False
    assert missed.data["confirm_ms"] is None
    assert "niet geantwoord" in missed.message
    assert "wacht niet" in started.message
    assert odd.data["module_confirmed"] is False
    assert odd.data["confirm_ms"] is None
    assert odd.data["reported"] is None


def _command_results(session: GatewaySession) -> list[dict]:
    return [event for event in session.buffer.snapshot() if event.get("type") == "command_result"]


@pytest.mark.asyncio
async def test_device_command_records_a_sent_result_and_skips_previews() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=[])
    gateway.command_body = {
        "ok": True,
        "module_confirmed": True,
        "confirm_ms": 42,
        "reported": {"state": "on"},
    }
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    session.devices = {"dev-trap": {"id": "dev-trap", "name": "Traphal"}}
    try:
        preview = await device_command(
            session, device_id="dev-trap", action="ON", confirmed=False
        )
        missing = await device_command(
            session, device_id="dev-trap", action="DIM", confirmed=True
        )
        sent = await device_command(
            session, device_id="dev-trap", action="ON", confirmed=True
        )
        gateway.command_status = 400
        gateway.command_body = {"ok": False, "error": "rejected"}
        failed = await device_command(
            session, device_id="dev-trap", action="OFF", confirmed=True
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert preview.data["kind"] == "confirmation_required"
    assert missing.data["kind"] == "confirmation_required"
    assert sent.data["sent"] is True
    assert failed.data["ok"] is False
    recorded = _command_results(session)
    assert len(recorded) == 2
    assert recorded[0]["device_id"] == "dev-trap"
    assert recorded[0]["name"] == "Traphal"
    assert recorded[0]["action"] == "ON"
    assert recorded[0]["ok"] is True
    assert recorded[0]["module_confirmed"] is True
    assert recorded[0]["confirm_ms"] == 42
    assert recorded[0]["reported"] == {"state": "on"}
    assert recorded[0]["confirmation_available"] is True
    assert "bevestigd" in recorded[0]["message"]
    assert "niet bevestigd" not in recorded[0]["message"]
    assert recorded[1]["ok"] is False
    assert recorded[1]["error"] == "rejected"
    assert "fout rejected" in recorded[1]["message"]
    assert "niet bevestigd" in recorded[1]["message"]


@pytest.mark.asyncio
async def test_decode_test_records_a_match_and_a_miss() -> None:
    session = GatewaySession("192.0.2.10:9", backoff_start=30, backoff_max=30)
    matched = await decode_test("I0154110", session)
    missed = await decode_test("I0100", session)
    events = [event for event in session.buffer.snapshot() if event.get("type") == "decode_result"]
    assert matched.data["matched"] is True
    assert len(events) == 2
    assert events[0]["hex"]
    assert events[0]["matched"] is True
    assert "kessel-lo" in str(events[0].get("dialect_id"))
    assert events[0]["fields"]
    assert "herkend" in events[0]["message"]
    assert missed.data["matched"] is False
    assert events[1]["matched"] is False
    assert "niet herkend" in events[1]["message"]
    assert "dialect_id" not in events[1]


@pytest.mark.asyncio
async def test_list_devices_shows_reachability_or_says_this_version_lacks_it() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    gateway.modules = [
        {
            "id": "module-a",
            "type": "relay",
            "name": "relay-a",
            "reachability": {
                "last_reply_at": "2026-10-08T12:00:00+00:00",
                "last_reply_ms": 18,
                "avg_reply_ms": 22,
                "missed_replies": 1,
            },
        },
        {
            "id": "module-b",
            "type": "dimmer",
            "name": "dimmer-b",
            "reachability": {
                "last_reply_at": None,
                "last_reply_ms": None,
                "avg_reply_ms": None,
                "missed_replies": 0,
            },
        },
        {"id": "module-c", "type": "input", "name": "input-c", "reachability": "kapot"},
    ]
    gateway.devices = [
        {
            "id": "device-a",
            "module_id": "module-a",
            "channel": 0,
            "device_type": "relay",
            "name": "lamp-a",
            "state": "off",
        }
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await list_devices(session)
    finally:
        await session.stop()
        await gateway.stop()
    rows = {row["id"]: row for row in result.data["modules"]}
    assert rows["module-a"]["reachability"]["last_reply_ms"] == 18
    assert rows["module-a"]["reachability"]["avg_reply_ms"] == 22
    assert rows["module-a"]["reachability"]["missed_replies"] == 1
    assert "18 ms" in result.message
    assert rows["module-b"]["reachability"]["last_reply_at"] is None
    assert "nog geen antwoord gemeten" in rows["module-b"]["reachability_sentence"]
    assert rows["module-c"]["reachability"] is None
    assert "niet beschikbaar in deze gatewayversie" in rows["module-c"]["reachability_note"]
    assert "module_reachability" not in (result.data.get("capabilities") or [])


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


@pytest.mark.asyncio
async def test_export_redacts_ipv6_macs_hosts_and_short_names() -> None:
    full_v6 = "2001:0db8:0000:0000:0000:0000:0000:0001"
    short_v6 = "2001:db8::1"
    embedded_v6 = "2001:db8::192.0.2.1"
    mac_colon = "aa:bb:cc:dd:ee:ff"
    mac_dash = "aa-bb-cc-dd-ee-ff"
    mac_dot = "aabb.ccdd.eeff"
    mac_bare = "aabbccddeeff"
    longer_hex = "aabbccddeeff00"
    session = GatewaySession("gwbox", backoff_start=30, backoff_max=30)
    session.tried = [
        {"host": "ipbgw.local", "port": 80, "source": "mdns", "result": "unreachable"}
    ]
    await session.buffer.append(
        {
            "type": "state_changed",
            "id": "device-a",
            "name": "wc",
            "room": "ke",
            "state": "on",
        }
    )
    note = (
        f"de wc in ke zag {full_v6} en {short_v6} en {embedded_v6} "
        f"plus {mac_colon} {mac_dash} {mac_dot} {mac_bare} "
        "via ipbgw.local en hub.example.test bij gwbox "
        f"maar gwboxlamp en wczolder en wc-lamp en file.txt en {longer_hex} blijven"
    )
    hidden = await export_session(session, note=note)
    blob = hidden.render()
    assert hidden.data["redacted"] is True
    for secret in (
        full_v6,
        short_v6,
        embedded_v6,
        "2001:db8",
        "192.0.2.1",
        mac_colon,
        mac_dash,
        mac_dot,
        "ipbgw.local",
        "hub.example.test",
    ):
        assert secret not in blob
    assert re.search(r"(?<![0-9A-Fa-f])" + mac_bare + r"(?![0-9A-Fa-f])", blob) is None
    assert re.search(r"(?<![A-Za-z0-9.-])gwbox(?![A-Za-z0-9.-])", blob) is None
    assert re.search(r"(?<![A-Za-z0-9_-])wc(?![A-Za-z0-9_-])", blob) is None
    assert re.search(r"(?<![A-Za-z0-9_-])ke(?![A-Za-z0-9_-])", blob) is None
    assert "gwboxlamp" in blob
    assert "wczolder" in blob
    assert "wc-lamp" in blob
    assert "file.txt" in blob
    assert longer_hex in blob
    states = [
        event
        for event in hidden.data["events"]
        if event.get("type") == "state_changed"
    ]
    assert states[0]["state"] == "on"
    assert states[0]["name"] == "wx"
    assert states[0]["room"] == "kx"
    rendered_note = hidden.data["notes"][0]["text"]
    assert rendered_note.startswith("de wx in kx zag [adres]")
    assert "[mac]" in rendered_note
    assert "gwboxlamp" in rendered_note
    raw = await export_session(session, redact=False)
    raw_blob = raw.render()
    assert raw.data["redacted"] is False
    for secret in (full_v6, short_v6, mac_colon, mac_dash, mac_dot, mac_bare, "ipbgw.local", "gwbox"):
        assert secret in raw_blob
    assert "wc" in raw_blob


@pytest.mark.asyncio
async def test_read_logs_redacts_the_same_address_and_name_gaps() -> None:
    from datetime import datetime, timezone

    full_v6 = "2001:0db8:0000:0000:0000:0000:0000:0001"
    short_v6 = "2001:db8::8a2e:370:7334"
    mac_colon = "aa:bb:cc:dd:ee:ff"
    mac_dash = "aa-bb-cc-dd-ee-ff"
    mac_dot = "aabb.ccdd.eeff"
    mac_bare = "aabbccddeeff"
    fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    message = (
        f"wc in ke zag {full_v6} en {short_v6} "
        f"plus {mac_colon} {mac_dash} {mac_dot} {mac_bare} "
        "via ipbgw.local en hub.example.test bij gwbox "
        "maar gwboxlamp en wczolder en file.txt blijven"
    )
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    gateway.devices = [
        {
            "id": "channel-a",
            "device_type": "relay",
            "name": "wc",
            "room": "ke",
        }
    ]
    gateway.log_lines = [
        {
            "type": "log",
            "ts": fresh,
            "level": "error",
            "logger": "gw",
            "message": message,
        }
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    session.tried = [
        {"host": "gwbox", "port": gateway.port, "source": "mdns_hostname", "result": "chosen"}
    ]
    try:
        hidden = await read_logs(
            session, seconds=2, since="2026-01-01T00:00:00Z", level="error", limit=5
        )
        shown = await read_logs(
            session,
            seconds=2,
            since="2026-01-01T00:00:00Z",
            level="error",
            limit=5,
            redact=False,
        )
    finally:
        await session.stop()
        await gateway.stop()
    text = hidden.data["lines"][0]["message"]
    blob = hidden.render()
    assert hidden.data["redacted"] is True
    assert text.startswith("[naam] in [naam] zag [adres]")
    assert "[mac]" in text
    assert "gwboxlamp" in text
    assert "wczolder" in text
    assert "file.txt" in text
    for secret in (
        full_v6,
        short_v6,
        "2001:db8",
        mac_colon,
        mac_dash,
        mac_dot,
        "ipbgw.local",
        "hub.example.test",
    ):
        assert secret not in blob
    assert re.search(r"(?<![0-9A-Fa-f])" + mac_bare + r"(?![0-9A-Fa-f])", text) is None
    assert re.search(r"(?<![A-Za-z0-9.-])gwbox(?![A-Za-z0-9.-])", text) is None
    assert re.search(r"(?<![A-Za-z0-9_-])wc(?![A-Za-z0-9_-])", text) is None
    assert re.search(r"(?<![A-Za-z0-9_-])ke(?![A-Za-z0-9_-])", text) is None
    raw_text = shown.data["lines"][0]["message"]
    assert shown.data["redacted"] is False
    assert raw_text == message
    assert "Deel deze tekst niet" in shown.message


@pytest.mark.asyncio
async def test_list_devices_and_recent_events_keep_short_names() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=[])
    gateway.devices = [
        {
            "id": "device-a",
            "module_id": "module-a",
            "channel": 0,
            "name": "wc",
            "room": "ke",
            "device_type": "relay",
            "state": "on",
            "active": True,
        }
    ]
    gateway.modules = [
        {"id": "module-a", "type": "relay", "model": "IP0200PoE", "name": "relay-a"}
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        listed = await list_devices(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert listed.data["devices"][0]["name"] == "wc"
    assert "wc" in listed.message
    await session.buffer.append(
        {
            "type": "state_changed",
            "id": "device-a",
            "name": "wc",
            "room": "ke",
            "state": "on",
        }
    )
    recent = await recent_events(session)
    assert recent.data["events"][0]["name"] == "wc"
    assert recent.data["events"][0]["room"] == "ke"


def test_unavailable_tools_name_the_missing_capability_or_switch() -> None:
    empty = {item["tool"]: item for item in unavailable_tools([], None)}
    assert empty["read_logs"]["missing"] == "log_stream"
    assert empty["capture_frames"]["missing"] == "udp_frame"
    assert empty["send_raw"]["missing"] == "raw_send"
    assert "capability raw_send ontbreekt" in empty["send_raw"]["reason"]

    partial = unavailable_tools(["log_stream"], True)
    assert [item["tool"] for item in partial] == ["capture_frames", "send_raw"]

    switched = {
        item["tool"]: item
        for item in unavailable_tools(["log_stream", "udp_frame", "raw_send"], False)
    }
    assert switched["send_raw"]["missing"] == "remote_debugging"
    assert switched["read_logs"]["missing"] == "remote_debugging"
    assert "schakelaar" in switched["send_raw"]["reason"]


@pytest.mark.asyncio
async def test_connection_status_explains_why_send_raw_cannot_run() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    blocked = {item["tool"]: item for item in result.data["unavailable_tools"]}
    assert "read_logs" not in blocked
    assert blocked["send_raw"]["missing"] == "raw_send"
    assert blocked["capture_frames"]["missing"] == "udp_frame"
    assert "send_raw" in result.message
    assert "raw_send" in result.message


@pytest.mark.asyncio
async def test_read_logs_without_log_stream_points_at_the_addon_log_tab() -> None:
    gateway = FakeGateway(remote_debugging=True, capabilities=[])
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await read_logs(session, seconds=0.2, limit=1)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["kind"] == "not_available"
    assert result.data["lines"] == []
    assert NOT_AVAILABLE_PHRASE in result.message
    assert "tabblad Log" in result.message
    assert gateway.received == []


@pytest.mark.asyncio
async def test_read_logs_switch_off_asks_to_enable_the_switch() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=["log_stream"])
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await read_logs(session, seconds=0.2, limit=1)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.message == MSG_REMOTE_DEBUGGING_OFF
    assert result.data["kind"] == "remote_debugging_off"


@pytest.mark.asyncio
async def test_read_logs_filters_and_redacts() -> None:
    from datetime import datetime, timezone

    host = _dotted(192, 0, 2, 10)
    fresh = datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
    gateway = FakeGateway(remote_debugging=True, capabilities=["log_stream"])
    gateway.devices = [{"id": "channel-a", "device_type": "relay", "name": "lamp-a"}]
    gateway.log_lines = [
        {
            "type": "log",
            "ts": "2020-01-01T00:00:00Z",
            "level": "error",
            "logger": "gw",
            "message": "oud",
        },
        {
            "type": "log",
            "ts": fresh,
            "level": "debug",
            "logger": "gw",
            "message": "stil",
        },
        {
            "type": "log",
            "ts": fresh,
            "level": "error",
            "logger": "gw",
            "message": f"lamp-a zag {host}",
        },
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        hidden = await read_logs(
            session, seconds=2, since="2026-01-01T00:00:00Z", level="error", limit=5
        )
        shown = await read_logs(
            session,
            seconds=2,
            since="2026-01-01T00:00:00Z",
            level="error",
            limit=5,
            redact=False,
        )
    finally:
        await session.stop()
        await gateway.stop()
    assert any(item.get("type") == "subscribe_logs" for item in gateway.received)
    texts = [line["message"] for line in hidden.data["lines"]]
    assert texts
    assert set(texts) == {"[naam] zag [adres]"}
    assert host not in hidden.render()
    assert "lamp-a" not in hidden.render()
    assert hidden.data["redacted"] is True
    raw_texts = [line["message"] for line in shown.data["lines"]]
    assert raw_texts
    assert set(raw_texts) == {f"lamp-a zag {host}"}
    assert "Deel deze tekst niet" in shown.message
    assert "oud" not in raw_texts
    assert "stil" not in raw_texts


@pytest.mark.asyncio
async def test_debug_log_level_reports_when_it_reverts() -> None:
    gateway = FakeGateway(
        remote_debugging=True,
        capabilities=["log_stream", "udp_frame", "raw_send"],
    )
    gateway.log_level_reply = {
        "type": "log_level",
        "ok": True,
        "level": "debug",
        "ttl": 900,
        "effective_level": "debug",
    }
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session, log_level="debug")
        again = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert "900" in result.message
    assert "15 minuten" in result.message
    assert "valt daarna terug" in result.message
    level = result.data["log_level"]
    assert level["reported"] is True
    assert level["effective_level"] == "debug"
    assert level["ttl"] == 900
    assert str(level["reverts_at"]).endswith("Z")
    assert 800 <= level["reverts_in_seconds"] <= 900
    assert again.data["log_level"]["effective_level"] == "debug"
    assert again.data["log_level"]["reverts_at"] == level["reverts_at"]
    assert result.message.count("Logniveau is nu") == 1
    assert "niet gemeld" not in result.message
    assert "Logniveau is nu" in again.message
    assert again.message.count("Logniveau is nu") == 1


def test_explicit_active_flag_from_the_gateway_wins() -> None:
    rows = {
        row["name"]: row
        for row in _feature_rows(
            {
                "remote_debugging": True,
                "capabilities": [
                    {"name": "log_stream", "active": False, "reason": "even geduld"},
                    "udp_frame",
                ],
            },
            remote=True,
            probed=None,
            reachable=True,
        )
    }
    assert rows["log_stream"]["supported"] is True
    assert rows["log_stream"]["active"] is False
    assert rows["log_stream"]["reason"] == "even geduld"
    assert rows["udp_frame"]["active"] is True
    assert rows["raw_send"]["supported"] is False
    assert rows["raw_send"]["active"] is False


@pytest.mark.asyncio
async def test_switch_off_keeps_button_and_state_and_drops_logs() -> None:
    gateway = FakeGateway(remote_debugging=False, capabilities=["log_stream"])
    gateway.log_lines = [
        {
            "type": "log",
            "ts": "2026-06-01T00:00:00Z",
            "level": "info",
            "logger": "gw",
            "message": "verborgen-regel",
        }
    ]
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        await session.ensure_started()
        assert await session.wait_until_connected(3)
        await gateway.push({"type": "state_changed", "id": "channel-a", "state": "on"})
        await gateway.push(
            {"type": "button_event", "id": "abcd1234", "action": "single_press"}
        )
        await session.buffer.wait_until(
            lambda event: event.get("type") == "button_event", 2, 0
        )
        events = await recent_events(session)
        logs = await read_logs(session, seconds=0.2, limit=5)
        status = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    kinds = {event.get("type") for event in events.data["events"]}
    assert kinds == {"state_changed", "button_event"}
    assert logs.message == MSG_REMOTE_DEBUGGING_OFF
    assert "verborgen-regel" not in logs.render()
    rows = {row["name"]: row for row in status.data["capability_status"]}
    assert rows["log_stream"]["supported"] is True
    assert rows["log_stream"]["active"] is False
    assert "Remote control (for debugging)" in rows["log_stream"]["reason"]
    assert "Knoppen" in rows["log_stream"]["reason"]
    assert rows["raw_send"]["supported"] is False
    assert rows["udp_frame"]["active"] is False
    assert not any(item.get("type") == "subscribe_logs" for item in gateway.received)


@pytest.mark.asyncio
async def test_switch_is_probed_when_status_omits_it() -> None:
    gateway = FakeGateway(
        remote_debugging=False,
        capabilities=["log_stream", "udp_frame", "raw_send"],
    )
    gateway.omit_remote_debugging = True
    await gateway.start()
    session = GatewaySession(f"localhost:{gateway.port}", backoff_start=0.05)
    try:
        result = await connection_status(session)
    finally:
        await session.stop()
        await gateway.stop()
    assert result.data["connected"] is True
    assert result.data["remote_debugging"] is None
    assert result.data["switch_active"] is False
    assert result.message == MSG_REMOTE_DEBUGGING_OFF
    rows = {row["name"]: row for row in result.data["capability_status"]}
    assert rows["log_stream"]["supported"] is True
    assert rows["log_stream"]["active"] is False
    assert rows["raw_send"]["active"] is False
    assert rows["udp_frame"]["active"] is False
    assert "Remote control (for debugging)" in rows["raw_send"]["reason"]
    assert any(item.get("type") == "subscribe_logs" for item in gateway.received)


@pytest.mark.asyncio
async def test_export_stamps_local_time_and_hides_legacy_dialect_ids() -> None:
    from ipbuilding_debug import dialect as dialect_mod

    incoming = next(
        f"input.{segment}.button_event"
        for segment, dialect in dialect_mod._LEGACY.items()
        if "input" in dialect.families
    )
    session = GatewaySession("localhost:9", backoff_start=30, backoff_max=30)
    await session.buffer.append(
        {
            "type": "log",
            "ts": "2026-01-02T03:04:05Z",
            "level": "info",
            "logger": "gw",
            "message": "hallo",
            "dialect_id": incoming,
        }
    )
    await session.buffer.append(
        {"type": "state_changed", "id": "channel-a", "state": "on"}
    )
    result = await export_session(session, note="lamp bleef aan")
    rendered = result.render()
    logged = next(event for event in result.data["events"] if event["type"] == "log")
    changed = next(
        event for event in result.data["events"] if event["type"] == "state_changed"
    )
    expected = datetime(2026, 1, 2, 3, 4, 5, tzinfo=timezone.utc).astimezone().isoformat(
        timespec="seconds"
    )
    assert logged["time_source"] == "gateway"
    assert logged["local_time"] == expected
    assert logged["dialect_id"] == "input.kessel-lo.button_event"
    assert logged["dialect_name"] == "Kessel-Lo"
    assert changed["time_source"] == "received"
    assert re.fullmatch(
        r"\d{4}-\d{2}-\d{2}T\d{2}:\d{2}:\d{2}[+-]\d{2}:\d{2}",
        changed["local_time"],
    )
    assert result.data["notes"][0]["time_source"] == "received"
    assert "local_time" in result.data["notes"][0]
    for segment in legacy_segments():
        assert f".{segment}." not in rendered
