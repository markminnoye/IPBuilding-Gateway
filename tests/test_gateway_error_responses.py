"""Tests for REST error response shape (plan §A).

Validates the typed error body contract:
- HTTP 4xx/5xx status codes instead of 200 + ok:false
- ``{"error": "<code>", "message": "...", "details": {...}}`` body
- ``schema_version: 2`` stamped on every successful JSON response
"""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock

import pytest
from aiohttp.test_utils import TestClient, TestServer

from gateway import gateway_api
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig


def _make_installation() -> InstallationConfig:
    return InstallationConfig._parse({
        "modules": [
            {
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "Keuken LED", "active": True, "max_watt": 60}
                ],
            },
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "channels": [],
            },
        ]
    })


def _make_api(installation: InstallationConfig) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(bus, reg, cfg)


def _json(payload: Any) -> Any:
    """Return a mock Request that resolves to a JSON body."""
    request = MagicMock()
    request.json = AsyncMock(return_value=payload)
    request.match_info = {}
    request.path = "/"
    return request


class TestApiErrorHelper:
    def test_basic_body_shape(self) -> None:
        err = gateway_api.ApiError(404, "device_not_found", "not there",
                                   details={"device_id": "x"})
        resp = gateway_api._json_error(err)
        assert resp.status == 404
        body = json.loads(resp.body)
        assert body == {
            "error": "device_not_found",
            "message": "not there",
            "details": {"device_id": "x"},
        }

    def test_omits_details_when_empty(self) -> None:
        err = gateway_api.ApiError(500, "internal")
        resp = gateway_api._json_error(err)
        body = json.loads(resp.body)
        assert "details" not in body
        assert body["error"] == "internal"


class TestErrorCodeMapping:
    @pytest.mark.asyncio
    async def test_missing_action_returns_400(self) -> None:
        api = _make_api(_make_installation())
        request = MagicMock()
        request.json = AsyncMock(return_value={})
        request.match_info = {"device_id": "10.10.1.30-0"}
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._post_command(request)
        assert exc.value.status == 400
        assert exc.value.code == "missing_action"

    @pytest.mark.asyncio
    async def test_unknown_device_returns_404(self) -> None:
        api = _make_api(_make_installation())
        request = MagicMock()
        request.json = AsyncMock(return_value={"action": "ON"})
        request.match_info = {"device_id": "10.10.1.99-0"}
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._post_command(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_inactive_channel_returns_422(self) -> None:
        inst = InstallationConfig._parse({
            "modules": [
                {
                    "name": "IP0200PoE",
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:be",
                    "channels": [
                        {"ch": 0, "name": "Inactive", "active": False, "max_watt": 60}
                    ],
                }
            ]
        })
        api = _make_api(inst)
        request = MagicMock()
        request.json = AsyncMock(return_value={"action": "ON"})
        request.match_info = {"device_id": "10.10.1.30-0"}
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._post_command(request)
        assert exc.value.status == 422
        assert exc.value.code == "channel_inactive"

    @pytest.mark.asyncio
    async def test_provision_autonomy_returns_501(self) -> None:
        api = _make_api(_make_installation())
        request = MagicMock()
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._post_autonomy(request)
        assert exc.value.status == 501
        assert exc.value.code == "not_implemented"

    @pytest.mark.asyncio
    async def test_get_unknown_device_returns_404(self) -> None:
        api = _make_api(_make_installation())
        request = MagicMock()
        request.match_info = {"device_id": "10.10.1.99-0"}
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._get_device(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_get_unknown_module_returns_404(self) -> None:
        api = _make_api(_make_installation())
        request = MagicMock()
        request.match_info = {"module_id": "00:11:22:33:44:55"}
        with pytest.raises(gateway_api.ApiError) as exc:
            await api._get_module(request)
        assert exc.value.status == 404
        assert exc.value.code == "module_not_found"


class TestSchemaVersionOnSuccess:
    def test_get_devices_includes_schema_version(self) -> None:
        api = _make_api(_make_installation())
        import asyncio
        loop = asyncio.new_event_loop()
        try:
            resp = loop.run_until_complete(api._get_devices(MagicMock()))
        finally:
            loop.close()
        body = json.loads(resp.body)
        assert body.get("schema_version") == 2
        assert "devices" in body

    def test_snapshot_includes_schema_version(self) -> None:
        api = _make_api(_make_installation())
        snap = api._build_snapshot()
        assert snap["schema_version"] == 2
