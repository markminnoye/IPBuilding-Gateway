"""Tests for experimental gateway.rest_api (backward-compat alias to rest_shim)."""

import json
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceRegistry, DeviceType
from gateway.installation import InstallationConfig
from gateway.rest_api import create_app


@pytest.fixture
def installation(tmp_path: Path) -> InstallationConfig:
    data = {
        "modules": [
            {
                "name": "relay_module",
                "ip": "10.10.1.30",
                "type": "relay",
                "channels": [
                    {"ch": 0,  "ipbox_id": 547},
                    {"ch": 10, "ipbox_id": 557},
                    {"ch": 16, "ipbox_id": 563},
                    {"ch": 23, "ipbox_id": 570},
                ],
            },
            {
                "name": "dimmer_module",
                "ip": "10.10.1.40",
                "type": "dimmer",
                "channels": [
                    {"ch": 0, "ipbox_id": 571},
                    {"ch": 1, "ipbox_id": 572},
                ],
            },
        ]
    }
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return InstallationConfig.load(p)


@pytest.fixture
def simulated_app(installation: InstallationConfig):
    cfg = GatewayConfig(
        simulated_mode=True,
        installation=installation,
        field_modules=installation.field_modules(),
    )
    from gateway.udp_bus import UDPBus
    udp = UDPBus(cfg)
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    return create_app(bus=udp, registry=reg, config=cfg)


@pytest.mark.asyncio
async def test_dim_action_rejects_out_of_range_value(simulated_app):
    async with TestClient(TestServer(simulated_app)) as client:
        for value in (250, -1, 101):
            resp = await client.get(
                f"/api/v1/action/action?id=571&actionType=DIM&value={value}"
            )
            assert resp.status == 400
            assert await resp.text() == "value must be 0-100 for DIM"


@pytest.mark.asyncio
async def test_dim_action_accepts_valid_value(simulated_app):
    async with TestClient(TestServer(simulated_app)) as client:
        resp = await client.get("/api/v1/action/action?id=571&actionType=DIM&value=50")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["id"] == 571