"""Live log stream and the remote-debugging refusal."""

from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import ApiError, GatewayAPI, _json_error
from gateway.installation import InstallationConfig
from gateway.log_stream import LogStream, redact
from gateway.remote_debug import (
    OPTION_LABEL_EN,
    OPTION_LABEL_NL,
    REMOTE_DEBUGGING_DISABLED,
    SETTINGS_PATH,
)


def _devices(tmp_path: Path) -> Path:
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"modules": []}), encoding="utf-8")
    return path


def _api(remote_debugging: bool, log_level: str = "INFO") -> GatewayAPI:
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
    cfg.log_level = log_level
    return GatewayAPI(MagicMock(), DeviceRegistry(), cfg)


class FakeWS:
    def __init__(self) -> None:
        self.sent: list[dict] = []
        self.closed = False

    async def send_json(self, msg: dict) -> None:
        self.sent.append(msg)


class SlowWS(FakeWS):
    def __init__(self) -> None:
        super().__init__()
        self.log_entered = asyncio.Event()
        self.release = asyncio.Event()

    async def send_json(self, msg: dict) -> None:
        if msg.get("type") == "log":
            self.log_entered.set()
            await self.release.wait()
        self.sent.append(msg)


class _JsonRequest:
    def __init__(self, body: object) -> None:
        self._body = body

    async def json(self) -> object:
        if isinstance(self._body, Exception):
            raise self._body
        return self._body


@pytest.fixture(autouse=True)
def _restore_root_logging():
    root = logging.getLogger()
    level = root.level
    handlers = list(root.handlers)
    yield
    root.setLevel(level)
    for handler in list(root.handlers):
        if handler not in handlers:
            root.removeHandler(handler)


def _assert_refusal(body: dict) -> None:
    assert body["error"] == REMOTE_DEBUGGING_DISABLED
    assert OPTION_LABEL_EN in body["message"]
    assert OPTION_LABEL_NL in body["message"]
    assert SETTINGS_PATH in body["message"]


async def _flush() -> None:
    for _ in range(5):
        await asyncio.sleep(0)


@pytest.mark.asyncio
async def test_refuses_log_calls_when_remote_debugging_is_off() -> None:
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    api = _api(False)
    try:
        ws = FakeWS()
        for raw in (
            {"type": "subscribe_logs", "min_level": "debug"},
            {"type": "unsubscribe_logs"},
            {"type": "set_log_level", "level": "debug", "ttl": 30},
        ):
            ws.sent.clear()
            await api._handle_ws_command(ws, json.dumps(raw))
            assert len(ws.sent) == 1
            _assert_refusal(ws.sent[0])
            assert ws.sent[0]["type"] == "error"
        assert root.level == logging.INFO
        assert api._log_stream._handler is None

        response = await api._api_error_middleware(
            _JsonRequest({"level": "debug", "ttl": 30}),
            api._post_debug_log_level,
        )
        assert response.status == 403
        _assert_refusal(json.loads(response.text))
        assert "schema_version" not in json.loads(response.text)

        status = json.loads((await api._get_status(MagicMock())).text)
        assert status["remote_debugging"] is False
        assert status["capabilities"] == ["log_stream", "udp_frame", "log_history"]
        assert root.level == logging.INFO
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_subscriber_gets_buffer_then_live_non_subscriber_gets_nothing() -> None:
    api = _api(True, log_level="DEBUG")
    logging.getLogger().setLevel(logging.DEBUG)
    try:
        api._log_stream.attach()
        logging.getLogger("gateway.udp_bus").debug("TX keepalive")
        logging.getLogger("gateway.state_poll").debug("RX status-poll")
        await _flush()

        subscribed = FakeWS()
        idle = FakeWS()
        await api._handle_ws_command(
            subscribed, json.dumps({"type": "subscribe_logs", "min_level": "debug"})
        )
        kinds = [msg["type"] for msg in subscribed.sent]
        assert kinds[-1] == "logs_subscribed"
        replay = [msg for msg in subscribed.sent if msg["type"] == "log"]
        assert [msg["message"] for msg in replay] == ["TX keepalive", "RX status-poll"]
        assert subscribed.sent[-1]["buffered"] == 2
        assert idle.sent == []

        before = len(subscribed.sent)
        logging.getLogger("gateway.udp_bus").debug("TX keepalive live")
        await _flush()
        live = subscribed.sent[before:]
        assert [msg["message"] for msg in live] == ["TX keepalive live"]
        assert idle.sent == []
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_set_log_level_is_temporary_and_not_stored(tmp_path: Path) -> None:
    path = _devices(tmp_path)
    before = path.read_bytes()
    os.environ["GATEWAY_LOG_LEVEL"] = "INFO"
    api = _api(True, log_level="INFO")
    api._cfg.devices_file = str(path)
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        ws = FakeWS()
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "set_log_level", "level": "debug", "ttl": 30}),
        )
        assert root.level == logging.DEBUG
        assert ws.sent[-1]["type"] == "log_level"
        assert ws.sent[-1]["effective_level"] == "debug"
        logging.getLogger("gateway.udp_bus").debug("TX keepalive")
        logging.getLogger("gateway.state_poll").debug("RX status-poll")
        await _flush()
        messages = [entry["message"] for entry in api._log_stream._buffer]
        assert "TX keepalive" in messages
        assert "RX status-poll" in messages

        owner = f"ws:{id(ws)}"
        api._log_stream._on_expire(owner)
        assert root.level == logging.INFO
        assert path.read_bytes() == before
        assert os.environ["GATEWAY_LOG_LEVEL"] == "INFO"
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_most_verbose_level_wins_then_the_remaining_client() -> None:
    api = _api(True, log_level="WARNING")
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    try:
        first = FakeWS()
        second = FakeWS()
        await api._handle_ws_command(
            first,
            json.dumps({"type": "set_log_level", "level": "debug", "ttl": 60}),
        )
        await api._handle_ws_command(
            second,
            json.dumps({"type": "set_log_level", "level": "info", "ttl": 60}),
        )
        assert root.level == logging.DEBUG
        await api._log_stream.disconnect(first)
        assert root.level == logging.INFO
        await api._log_stream.disconnect(second)
        assert root.level == logging.WARNING
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_last_subscriber_leaving_restores_baseline() -> None:
    api = _api(True, log_level="WARNING")
    root = logging.getLogger()
    root.setLevel(logging.WARNING)
    try:
        ws = FakeWS()
        await api._handle_ws_command(
            ws, json.dumps({"type": "subscribe_logs", "min_level": "info"})
        )
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "set_log_level", "level": "debug", "ttl": 60}),
        )
        assert root.level == logging.DEBUG
        await api._handle_ws_command(ws, json.dumps({"type": "unsubscribe_logs"}))
        assert ws.sent[-1] == {"type": "logs_unsubscribed"}
        assert root.level == logging.WARNING
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_quieter_request_keeps_baseline() -> None:
    api = _api(True, log_level="INFO")
    root = logging.getLogger()
    root.setLevel(logging.INFO)
    try:
        ws = FakeWS()
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "set_log_level", "level": "warning", "ttl": 30}),
        )
        assert root.level == logging.INFO
        assert ws.sent[-1]["effective_level"] == "info"
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_slow_client_is_dropped_and_commands_still_run() -> None:
    api = _api(True, log_level="DEBUG")
    api._log_stream = LogStream(baseline_level=logging.DEBUG, queue_size=1)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    ws = SlowWS()
    try:
        await api._handle_ws_command(
            ws, json.dumps({"type": "subscribe_logs", "min_level": "debug"})
        )
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "set_log_level", "level": "debug", "ttl": 30}),
        )
        logging.getLogger("gateway.udp_bus").debug("TX keepalive one")
        logging.getLogger("gateway.udp_bus").debug("TX keepalive two")
        await asyncio.wait_for(ws.log_entered.wait(), timeout=1)
        assert any(msg.get("type") == "log_dropped" for msg in ws.sent)

        started = asyncio.get_running_loop().time()
        await api._handle_ws_command(
            ws,
            json.dumps({"type": "command", "id": "missing-0", "action": "ON"}),
        )
        elapsed = asyncio.get_running_loop().time() - started
        assert elapsed < 0.2
        assert ws.sent[-1]["type"] == "command_result"
        assert ws.sent[-1]["ok"] is False
    finally:
        ws.release.set()
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_library_logs_are_ignored_and_handler_does_not_recurse(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    stream = LogStream(baseline_level=logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)

    def chatty(message: str) -> str:
        logging.getLogger("gateway.udp_bus").info("nested %s", message)
        return message

    monkeypatch.setattr("gateway.log_stream.redact", chatty)
    try:
        stream.attach()
        logging.getLogger("aiohttp.web").debug("frame sent")
        logging.getLogger("websockets.protocol").debug("frame sent")
        logging.getLogger("gateway.udp_bus").info("hello")
        await _flush()
        messages = [entry["message"] for entry in stream._buffer]
        assert messages == ["hello"]
        assert all("frame sent" not in message for message in messages)
    finally:
        stream.detach()


def test_redacts_secrets_and_keeps_payload_hex() -> None:
    raw = (
        "Authorization: Bearer abcdef token=abcdef "
        "password=s3cret api_key: s3cret "
        "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
        ".eyJzdWIiOiIxIn0.signaturekeep "
        "TX keepalive aa bb cc"
    )
    cleaned = redact(raw)
    assert "abcdef" not in cleaned
    assert "s3cret" not in cleaned
    assert "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9" not in cleaned
    assert "[redacted]" in cleaned
    assert "aa bb cc" in cleaned


@pytest.mark.asyncio
async def test_rest_level_rate_limit_and_ttl_validation() -> None:
    api = _api(True, log_level="INFO")
    api._log_stream = LogStream(baseline_level=logging.INFO, rate_limit=2)
    try:
        for _ in range(2):
            response = await api._api_error_middleware(
                _JsonRequest({"level": "debug", "ttl": 30}),
                api._post_debug_log_level,
            )
            body = json.loads(response.text)
            assert response.status == 200
            assert body["ok"] is True
            assert body["effective_level"] == "debug"

        limited = await api._api_error_middleware(
            _JsonRequest({"level": "debug", "ttl": 30}),
            api._post_debug_log_level,
        )
        assert limited.status == 429
        assert json.loads(limited.text)["error"] == "log_level_rate_limited"

        invalid = await api._api_error_middleware(
            _JsonRequest({"level": "debug", "ttl": True}),
            api._post_debug_log_level,
        )
        assert invalid.status == 400
        assert json.loads(invalid.text)["error"] == "invalid_ttl"
    finally:
        api._log_stream.detach()


@pytest.mark.asyncio
async def test_log_record_from_another_thread_uses_the_loop() -> None:
    stream = LogStream(baseline_level=logging.DEBUG)
    root = logging.getLogger()
    root.setLevel(logging.DEBUG)
    try:
        stream.attach()
        calls: list[bool] = []
        original = stream._loop.call_soon_threadsafe

        def wrapped(*args, **kwargs):
            calls.append(True)
            return original(*args, **kwargs)

        stream._loop.call_soon_threadsafe = wrapped  # type: ignore[method-assign]
        thread = threading.Thread(
            target=lambda: logging.getLogger("gateway.udp_bus").debug("TX keepalive")
        )
        thread.start()
        thread.join(timeout=1)
        await _flush()
        assert calls
        assert stream._buffer[-1]["message"] == "TX keepalive"
        assert stream._buffer[-1]["logger"] == "gateway.udp_bus"
    finally:
        stream.detach()


@pytest.mark.asyncio
async def test_ws_and_rest_refusal_share_one_sentence() -> None:
    api = _api(False)
    ws = FakeWS()
    await api._handle_ws_command(ws, json.dumps({"type": "subscribe_logs"}))
    try:
        await api._post_debug_log_level(_JsonRequest({"level": "info", "ttl": 5}))
    except ApiError as exc:
        rest = json.loads(_json_error(exc).text)
    else:
        raise AssertionError("expected ApiError")
    assert ws.sent[0]["error"] == rest["error"] == REMOTE_DEBUGGING_DISABLED
    assert ws.sent[0]["message"] == rest["message"]
