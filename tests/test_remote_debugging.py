"""Remote-debugging option on status and the WebSocket snapshot."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from gateway.capabilities import CAPABILITIES
from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import GatewayAPI
from gateway.installation import InstallationConfig


def _devices(tmp_path: Path) -> Path:
    path = tmp_path / "devices.json"
    path.write_text(json.dumps({"modules": []}), encoding="utf-8")
    return path


def test_remote_debugging_defaults_off() -> None:
    assert GatewayConfig().remote_debugging is False
    assert CAPABILITIES == ("log_stream", "udp_frame")


def test_from_env_remote_debugging(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(_devices(tmp_path)))
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)
    monkeypatch.delenv("GATEWAY_REMOTE_DEBUGGING", raising=False)
    assert GatewayConfig.from_env().remote_debugging is False

    monkeypatch.setenv("GATEWAY_REMOTE_DEBUGGING", "1")
    assert GatewayConfig.from_env().remote_debugging is True


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
    return GatewayAPI(MagicMock(), DeviceRegistry(), cfg)


@pytest.mark.asyncio
async def test_status_and_snapshot_include_toolkit_fields() -> None:
    api = _api(True)
    response = await api._get_status(MagicMock())
    body = json.loads(response.text)
    assert body["remote_debugging"] is True
    assert body["capabilities"] == ["log_stream", "udp_frame"]
    assert "version" in body

    snap = api._build_snapshot()
    gateway_status = snap["gateway_status"]
    assert gateway_status["remote_debugging"] is True
    assert gateway_status["capabilities"] == ["log_stream", "udp_frame"]
    assert "actions" not in gateway_status

    off = _api(False)
    off_body = json.loads((await off._get_status(MagicMock())).text)
    assert off_body["remote_debugging"] is False
    assert off._build_snapshot()["gateway_status"]["remote_debugging"] is False
