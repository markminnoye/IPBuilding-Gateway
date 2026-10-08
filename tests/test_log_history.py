"""In-memory log ring: time and level filters, only while remote control is on."""

from __future__ import annotations

import asyncio
import json
import logging
from datetime import datetime, timedelta, timezone
from unittest.mock import MagicMock

import pytest

from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import ApiError, GatewayAPI
from gateway.installation import InstallationConfig
from gateway.log_stream import LogStream


def _iso(age_s: float) -> str:
    when = datetime.now(timezone.utc) - timedelta(seconds=age_s)
    return when.isoformat(timespec="milliseconds").replace("+00:00", "Z")


def _line(message: str, level: str, age_s: float) -> dict:
    return {
        "type": "log",
        "ts": _iso(age_s),
        "level": level,
        "logger": "gateway.udp_bus",
        "message": message,
    }


def _open(stream: LogStream) -> None:
    stream._handler = logging.NullHandler()


def _api(remote_debugging: bool) -> GatewayAPI:
    installation = InstallationConfig._parse({"modules": []})
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.buttons_via_ha = True
    cfg.hub_role = "slave"
    cfg.input_mode_label = "Slave"
    cfg.multi_press = False
    cfg.multi_press_window_ms = 350
    cfg.remote_debugging = remote_debugging
    cfg.log_level = "INFO"
    return GatewayAPI(MagicMock(), DeviceRegistry(), cfg)


class _Request:
    def __init__(self, **values: str) -> None:
        self.query = values


class _WS:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


def test_ring_drops_lines_by_age_and_count() -> None:
    stream = LogStream(buffer_size=2, max_age_s=300)
    _open(stream)
    stream._on_entry(_line("ancient", "error", 400))
    stream._on_entry(_line("first", "info", 20))
    stream._on_entry(_line("second", "warning", 10))
    stream._on_entry(_line("third", "error", 5))
    assert [entry["message"] for entry in stream._buffer] == ["second", "third"]


def test_history_filters_since_and_level() -> None:
    stream = LogStream(max_age_s=300)
    _open(stream)
    stream._on_entry(_line("old warning", "warning", 90))
    stream._on_entry(_line("recent info", "info", 20))
    stream._on_entry(_line("recent warning", "warning", 10))
    result = stream.history("warning", _iso(60))
    assert result["min_level"] == "warning"
    assert [line["message"] for line in result["lines"]] == ["recent warning"]

    last_minute = stream.history("info", _iso(60))
    assert [line["message"] for line in last_minute["lines"]] == [
        "recent info",
        "recent warning",
    ]


def test_invalid_since_is_rejected() -> None:
    stream = LogStream()
    with pytest.raises(Exception) as caught:
        stream.history("info", "60")
    assert caught.value.code == "invalid_since"  # type: ignore[attr-defined]


@pytest.mark.asyncio
async def test_detach_clears_the_ring_and_later_lines_are_ignored() -> None:
    stream = LogStream()
    stream.attach()
    stream._on_entry(_line("kept", "warning", 1))
    assert stream._buffer
    stream.detach()
    assert list(stream._buffer) == []
    stream._on_entry(_line("later", "warning", 1))
    assert list(stream._buffer) == []


@pytest.mark.asyncio
async def test_read_logs_returns_the_last_minute() -> None:
    api = _api(True)
    api._log_stream.attach()
    try:
        api._log_stream._on_entry(_line("too old", "error", 90))
        api._log_stream._on_entry(_line("in the minute", "warning", 15))
        api._log_stream._on_entry(_line("info in the minute", "info", 5))
        response = await api._get_debug_logs(
            _Request(since=_iso(60), min_level="warning")  # type: ignore[arg-type]
        )
        body = json.loads(response.text)
        assert response.status == 200
        assert body["ok"] is True
        assert body["schema_version"] == 2
        assert body["min_level"] == "warning"
        assert body["since"]
        assert [line["message"] for line in body["lines"]] == ["in the minute"]

        ws = _WS()
        await api._handle_ws_command(
            ws,  # type: ignore[arg-type]
            json.dumps(
                {
                    "type": "subscribe_logs",
                    "min_level": "warning",
                    "since": _iso(60),
                }
            ),
        )
        replay = [msg for msg in ws.sent if msg["type"] == "log"]
        assert [msg["message"] for msg in replay] == ["in the minute"]
        assert ws.sent[-1]["type"] == "logs_subscribed"
        assert ws.sent[-1]["buffered"] == 1
        assert ws.sent[-1]["min_level"] == "warning"
        assert ws.sent[-1]["since"]
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_logs_are_refused_and_empty_when_remote_control_is_off() -> None:
    api = _api(False)
    logging.getLogger("gateway.udp_bus").error("should stay out")
    await asyncio.sleep(0)
    assert list(api._log_stream._buffer) == []
    with pytest.raises(ApiError) as caught:
        await api._get_debug_logs(_Request())  # type: ignore[arg-type]
    assert caught.value.status == 403
    assert caught.value.code == "remote_debugging_disabled"
    status = json.loads((await api._get_status(MagicMock())).text)
    assert "log_history" in status["capabilities"]
    assert status["remote_debugging"] is False


@pytest.mark.asyncio
async def test_bad_since_on_the_socket_is_an_error_frame() -> None:
    api = _api(True)
    ws = _WS()
    try:
        await api._handle_ws_command(
            ws,  # type: ignore[arg-type]
            json.dumps({"type": "subscribe_logs", "since": "yesterday"}),
        )
        assert ws.sent[-1]["type"] == "error"
        assert ws.sent[-1]["error"] == "invalid_since"
    finally:
        api._log_stream.detach()
