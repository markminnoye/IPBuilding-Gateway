"""Integration tests for installation API endpoints."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry
from gateway.gateway_api import GatewayAPI
from gateway.installation import InstallationConfig
from gateway.udp_bus import UDPBus


@pytest.fixture
def devices_file(tmp_path: Path) -> Path:
    data = {
        "modules": [{
            "name": "IP0200PoE",
            "ip": "10.10.1.30",
            "type": "relay",
            "mac": "00:24:77:52:ac:be",
            "channels": [{
                "ch": 0,
                "name": "Keuken LED",
                "room": "Keuken",
                "semantic_type": "light",
                "active": True,
                "max_watt": 60,
            }],
        }],
        "buttons": [],
    }
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


def _make_api(devices_file: Path) -> GatewayAPI:
    inst = InstallationConfig.load(devices_file)
    cfg = GatewayConfig(
        hub_ip="10.10.1.1",
        api_host="127.0.0.1",
        api_port=0,
        devices_file=str(devices_file),
        installation=inst,
    )
    bus = MagicMock(spec=UDPBus)
    reg = DeviceRegistry()
    for mc in inst.modules:
        reg.register_module(mc.ip, mc.type)
    api = GatewayAPI(bus, reg, cfg)
    applied: list[InstallationConfig] = []

    def _on_changed(new_inst: InstallationConfig) -> None:
        cfg.installation = new_inst
        applied.append(new_inst)

    api.set_installation_changed_callback(_on_changed)
    api._applied = applied  # type: ignore[attr-defined]
    return api


@pytest.mark.asyncio
async def test_get_installation(devices_file: Path) -> None:
    api = _make_api(devices_file)
    app = web.Application()
    app.router.add_get("/api/v1/installation", api._get_installation)
    async with TestClient(TestServer(app)) as client:
        resp = await client.get("/api/v1/installation")
        assert resp.status == 200
        body = await resp.json()
        assert len(body["modules"]) == 1
        assert body["buttons"] == []


@pytest.mark.asyncio
async def test_validate_rejects_unknown_type(devices_file: Path) -> None:
    api = _make_api(devices_file)
    app = web.Application()
    app.router.add_post("/api/v1/installation/validate", api._post_installation_validate)
    body = {
        "mode": "append_modules",
        "modules": [{"ip": "10.10.1.55", "type": "unknown", "channels": []}],
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/v1/installation/validate", json=body)
        assert resp.status == 422
        result = await resp.json()
        assert result["ok"] is False


@pytest.mark.asyncio
async def test_apply_merge_and_reload(devices_file: Path) -> None:
    api = _make_api(devices_file)
    app = web.Application()
    app.router.add_post("/api/v1/installation/apply", api._post_installation_apply)
    body = {
        "mode": "merge_modules",
        "modules": [{
            "ip": "10.10.1.30",
            "type": "relay",
            "mac": "00:24:77:52:ac:be",
            "firmware": "5.2",
            "channels": [],
        }],
    }
    async with TestClient(TestServer(app)) as client:
        resp = await client.post("/api/v1/installation/apply", json=body)
        assert resp.status == 200
        result = await resp.json()
        assert result["ok"] is True
        assert result["reload"] is True
        assert result["applied"]["modules"] == 1

    reloaded = InstallationConfig.load(devices_file)
    assert reloaded.module_by_ip("10.10.1.30").firmware == "5.2"
    assert len(api._applied) == 1  # type: ignore[attr-defined]
