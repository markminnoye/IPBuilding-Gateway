"""Live field-bus frames and the remote-debugging refusal."""

from __future__ import annotations

import asyncio
import json
from unittest.mock import MagicMock

import pytest

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import GatewayAPI
from gateway.installation import InstallationConfig
from gateway.remote_debug import (
    OPTION_LABEL_EN,
    OPTION_LABEL_NL,
    REMOTE_DEBUGGING_DISABLED,
    SETTINGS_PATH,
)
from gateway.udp_bus import UDPBus
from gateway.udp_frames import UdpFrameHub
from gateway.payloads.dialects import TORHOUT

# Older-generation command echo: the reply bytes match the command.
_ECHO = b"S00001000"


def _api(bus: object, remote_debugging: bool) -> GatewayAPI:
    installation = InstallationConfig._parse({"modules": []})
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "localhost"
    cfg.api_port = 8080
    cfg.buttons_via_ha = True
    cfg.hub_role = "slave"
    cfg.input_mode_label = "Slave"
    cfg.multi_press = False
    cfg.multi_press_window_ms = 350
    cfg.remote_debugging = remote_debugging
    cfg.log_level = "INFO"
    return GatewayAPI(bus, DeviceRegistry(), cfg)


def _bus() -> UDPBus:
    installation = InstallationConfig._parse({"modules": []})
    cfg = GatewayConfig(
        simulated_mode=True,
        bind_ip="gateway",
        installation=installation,
    )
    bus = UDPBus(cfg)
    bus.register_simulated_reply(_ECHO, _ECHO)
    return bus


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


class SlowWS(FakeWS):
    def __init__(self) -> None:
        super().__init__()
        self.frame_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def send_json(self, msg: dict) -> None:
        if msg.get("type") == "udp_frame":
            self.frame_entered.set()
            await self.release.wait()
        self.sent.append(msg)


def _assert_refusal(body: dict) -> None:
    assert body["type"] == "error"
    assert body["error"] == REMOTE_DEBUGGING_DISABLED
    assert OPTION_LABEL_EN in body["message"]
    assert OPTION_LABEL_NL in body["message"]
    assert SETTINGS_PATH in body["message"]


async def _flush() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_udp_frames_refused_when_remote_debugging_is_off() -> None:
    bus = MagicMock()
    api = _api(bus, False)
    ws = FakeWS()
    for raw in (
        {"type": "subscribe_udp_frames"},
        {"type": "unsubscribe_udp_frames"},
    ):
        ws.sent.clear()
        await api._handle_ws_command(ws, json.dumps(raw))
        assert len(ws.sent) == 1
        _assert_refusal(ws.sent[0])
    assert api._udp_frame_listener is False
    bus.add_frame_listener.assert_not_called()
    status = json.loads((await api._get_status(MagicMock())).text)
    assert status["remote_debugging"] is False
    assert status["capabilities"] == ["log_stream", "udp_frame", "raw_send"]


@pytest.mark.asyncio
async def test_subscriber_sees_command_and_echo() -> None:
    bus = _bus()
    api = _api(bus, True)
    subscribed = FakeWS()
    idle = FakeWS()
    try:
        await api._handle_ws_command(
            subscribed, json.dumps({"type": "subscribe_udp_frames"})
        )
        assert subscribed.sent[-1] == {"type": "udp_frames_subscribed"}
        await bus.send_command("module", _ECHO)
        await _flush()
        frames = [msg for msg in subscribed.sent if msg["type"] == "udp_frame"]
        assert [msg["direction"] for msg in frames] == ["tx", "rx"]
        assert frames[0]["hex"] == frames[1]["hex"] == _ECHO.hex()
        assert frames[0]["src"] == "gateway"
        assert frames[0]["dst"] == "module"
        assert frames[1]["src"] == "module"
        assert frames[1]["dst"] == "gateway"
        assert frames[0]["dialect_id"] == TORHOUT.message_type("relay", "command_reply")
        assert frames[1]["decoded"]["family"] == "relay_command_reply"
        assert idle.sent == []
    finally:
        api._detach_udp_frames()


@pytest.mark.asyncio
async def test_unsubscribe_stops_frames() -> None:
    bus = _bus()
    api = _api(bus, True)
    ws = FakeWS()
    try:
        await api._handle_ws_command(ws, json.dumps({"type": "subscribe_udp_frames"}))
        await api._handle_ws_command(
            ws, json.dumps({"type": "unsubscribe_udp_frames"})
        )
        assert ws.sent[-1] == {"type": "udp_frames_unsubscribed"}
        await bus.send_command("module", _ECHO)
        await _flush()
        assert all(msg["type"] != "udp_frame" for msg in ws.sent)
    finally:
        api._detach_udp_frames()


@pytest.mark.asyncio
async def test_unknown_payload_has_no_decode() -> None:
    bus = _bus()
    api = _api(bus, True)
    ws = FakeWS()
    try:
        await api._handle_ws_command(ws, json.dumps({"type": "subscribe_udp_frames"}))
        await bus.send_command("module", b"\xff\x00")
        await _flush()
        frames = [msg for msg in ws.sent if msg["type"] == "udp_frame"]
        assert len(frames) == 1
        assert frames[0]["direction"] == "tx"
        assert frames[0]["decoded"] is None
        assert frames[0]["dialect_id"] is None
        assert frames[0]["hex"] == "ff00"
    finally:
        api._detach_udp_frames()


@pytest.mark.asyncio
async def test_slow_client_reports_dropped_without_stalling() -> None:
    bus = _bus()
    api = _api(bus, True)
    api._udp_frames = UdpFrameHub(queue_size=1)
    ws = SlowWS()
    try:
        await api._handle_ws_command(ws, json.dumps({"type": "subscribe_udp_frames"}))
        await bus.send_command("module", _ECHO)
        await asyncio.wait_for(ws.frame_entered.wait(), timeout=1)
        assert any(msg.get("type") == "udp_frame_dropped" for msg in ws.sent)
        assert any(msg.get("dropped", 0) >= 1 for msg in ws.sent)

        started = asyncio.get_running_loop().time()
        for _ in range(20):
            await bus.send_command("module", _ECHO)
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "command", "id": "missing-0", "action": "ON"}),
        )
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 0.2
        assert ws.sent[-1]["type"] == "command_result"
    finally:
        ws.release.set()
        api._detach_udp_frames()
