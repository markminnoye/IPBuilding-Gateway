"""Tests for GET/POST /api/v1/devices/export|import|reset (backup & restore)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway import gateway_api
from gateway.auto_discovery import DiscoveryConfig
from gateway.device_config import installation_to_raw_dict
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig


def _make_installation(modules: list[dict[str, Any]] | None = None) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules or []})


def _write_devices_file(path: Path, installation: InstallationConfig) -> None:
    path.write_text(json.dumps(installation_to_raw_dict(installation), indent=2), encoding="utf-8")


def _make_api(
    installation: InstallationConfig,
    devices_file: Path,
    metadata_cache: gateway_api.ModuleMetadataCache | None = None,
) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.discovery = DiscoveryConfig(lock_timeout_s=5.0)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(bus, reg, cfg, metadata_cache=metadata_cache)


def _app_with_routes(api: gateway_api.GatewayAPI) -> web.Application:
    app = web.Application(middlewares=[api._api_error_middleware])
    app.router.add_get("/api/v1/devices/export", api._get_devices_export)
    app.router.add_get("/api/v1/devices/{device_id}", api._get_device)
    return app


@pytest.fixture
def sample_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP0200PoE",
            "ip": "10.10.1.30",
            "type": "relay",
            "mac": "00:24:77:52:ac:be",
            "channels": [
                {
                    "ch": 0,
                    "name": "Keuken LED",
                    "room": "Keuken",
                    "semantic_type": "light",
                    "active": True,
                    "max_watt": 60,
                }
            ],
        }
    ])


class TestExport:
    @pytest.mark.asyncio
    async def test_export_returns_file_bytes_with_attachment_header(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        on_disk_bytes = devices_file.read_bytes()

        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            assert resp.status == 200
            assert "attachment" in resp.headers["Content-Disposition"]
            assert "devices.json" in resp.headers["Content-Disposition"]
            body = await resp.read()
            assert body == on_disk_bytes

    @pytest.mark.asyncio
    async def test_export_missing_file_returns_404(self, tmp_path: Path) -> None:
        devices_file = tmp_path / "does_not_exist.json"
        api = _make_api(_make_installation(), devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            assert resp.status == 404
            body = await resp.json()
            assert body["error"] == "devices_file_missing"

    @pytest.mark.asyncio
    async def test_export_route_not_shadowed_by_dynamic_device_route(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        """Regression: /api/v1/devices/export must not be swallowed by
        GET /api/v1/devices/{device_id} as device_id="export"."""
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices/export")
            # A 404 device_not_found here (rather than 200 with Content-Disposition)
            # would mean the dynamic route won — the real bug this test guards against.
            assert resp.status == 200
            assert "Content-Disposition" in resp.headers
