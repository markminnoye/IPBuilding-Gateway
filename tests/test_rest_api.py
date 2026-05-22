"""Tests for experimental gateway.rest_api."""

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import GatewayConfig
from gateway.rest_api import create_app


@pytest.fixture
def simulated_app():
    return create_app(config=GatewayConfig(simulated_mode=True))


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
