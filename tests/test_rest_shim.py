"""Tests for gateway.rest_shim (IPBox-compat REST with registry)."""

import json
import tempfile
from pathlib import Path

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import GatewayConfig
from gateway.device_registry import DeviceKey, DeviceRegistry
from gateway.types import DeviceType
from gateway.installation import InstallationConfig
from gateway.rest_shim import create_app
from gateway.udp_bus import UDPBus


_STANDARD_INSTALLATION = {
    "modules": [
        {
            "name": "relay_module",
            "ip": "10.10.1.30",
            "type": "relay",
            "channels": [
                {"ch": 0, "id": 547},
                {"ch": 10, "id": 557},
                {"ch": 16, "id": 563},
                {"ch": 23, "id": 570},
            ],
        },
        {
            "name": "dimmer_module",
            "ip": "10.10.1.40",
            "type": "dimmer",
            "channels": [
                {"ch": 0, "id": 571},
                {"ch": 1, "id": 572},
            ],
        },
        {
            "name": "input_module",
            "ip": "10.10.1.50",
            "type": "input",
            "channels": [],
        },
    ]
}


@pytest.fixture
def installation(tmp_path: Path) -> InstallationConfig:
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(_STANDARD_INSTALLATION), encoding="utf-8")
    return InstallationConfig.load(p)


def _setup(installation: InstallationConfig) -> tuple[GatewayConfig, UDPBus, DeviceRegistry]:
    cfg = GatewayConfig(
        simulated_mode=True,
        installation=installation,
        field_modules=installation.field_modules(),
    )
    bus = UDPBus(cfg)
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    return cfg, bus, reg


@pytest.fixture
def shim_app(installation: InstallationConfig):
    cfg, bus, reg = _setup(installation)
    return create_app(bus=bus, registry=reg, config=cfg)


@pytest.fixture
def shim_app_with_state(installation: InstallationConfig):
    cfg, bus, reg = _setup(installation)
    from gateway.udp_bus import UDPPacket

    reg.handle_packet(UDPPacket(
        data=b"I00000100", src_ip="10.10.1.30", src_port=1001,
        dst_ip="", dst_port=0, monotonic_ts=0.0,
    ))
    return create_app(bus=bus, registry=reg, config=cfg)


@pytest.mark.asyncio
async def test_dim_action_rejects_out_of_range_value(shim_app):
    async with TestClient(TestServer(shim_app)) as client:
        for value in (250, -1, 101):
            resp = await client.get(
                f"/api/v1/action/action?id=571&actionType=DIM&value={value}"
            )
            assert resp.status == 400
            assert await resp.text() == "value must be 0-100 for DIM"


@pytest.mark.asyncio
async def test_dim_action_accepts_valid_value(shim_app):
    async with TestClient(TestServer(shim_app)) as client:
        resp = await client.get("/api/v1/action/action?id=571&actionType=DIM&value=50")
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert body["id"] == 571


@pytest.mark.asyncio
async def test_comp_items_returns_registry_state(shim_app_with_state):
    async with TestClient(TestServer(shim_app_with_state)) as client:
        resp = await client.get("/api/v1/comp/items")
        assert resp.status == 200
        items = await resp.json()
        relay_items = [i for i in items if i["type"] == "relay"]
        assert len(relay_items) > 0

        ch0 = next((i for i in relay_items if i["channel"] == 0), None)
        assert ch0 is not None
        assert ch0["state"] == "on"


@pytest.mark.asyncio
async def test_comp_items_unknown_state(shim_app):
    """Without poll data, relay state should be 'unknown'."""
    async with TestClient(TestServer(shim_app)) as client:
        resp = await client.get("/api/v1/comp/items")
        items = await resp.json()
        relay_items = [i for i in items if i["type"] == "relay"]
        for item in relay_items:
            assert item["state"] == "unknown"


@pytest.mark.asyncio
async def test_relay_on_value_zero_sends_off(installation: InstallationConfig):
    """IPBox REST uses actionType=ON with value=0 for OFF; must not encode as ON."""
    cfg, bus, reg = _setup(installation)
    sent: list[bytes] = []
    original = bus.send_command

    async def track(ip, payload):
        sent.append(payload)
        await original(ip, payload)

    bus.send_command = track  # type: ignore[method-assign]
    app = create_app(bus=bus, registry=reg, config=cfg)

    async with TestClient(TestServer(app)) as client:
        resp = await client.get(
            "/api/v1/action/action?id=547&actionType=ON&value=0"
        )
        assert resp.status == 200
        body = await resp.json()
        assert body["ok"] is True
        assert sent[-1].startswith(b"C")

        resp = await client.get(
            "/api/v1/action/action?id=547&actionType=ON&value=1"
        )
        assert resp.status == 200
        assert sent[-1].startswith(b"S")


@pytest.mark.asyncio
async def test_action_unknown_id(shim_app):
    """Unknown component id returns 404."""
    async with TestClient(TestServer(shim_app)) as client:
        resp = await client.get("/api/v1/action/action?id=9999&actionType=ON")
        assert resp.status == 404
        assert b"unknown component id" in await resp.content.read()


@pytest.mark.asyncio
async def test_backward_compat_import():
    """The old gateway.rest_api module should still work."""
    from gateway.rest_api import RESTApp, create_app as old_create_app

    assert RESTApp is not None
    assert old_create_app is not None