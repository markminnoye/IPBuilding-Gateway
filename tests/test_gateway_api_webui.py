"""Tests for GET / — the self-contained ingress web UI."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer
from unittest.mock import MagicMock

from gateway import gateway_api
from gateway.auto_discovery import DiscoveryConfig
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig


def _make_api(tmp_path: Path) -> gateway_api.GatewayAPI:
    installation = InstallationConfig._parse({"modules": []})
    devices_file = tmp_path / "devices.json"
    devices_file.write_text('{"modules": [], "buttons": []}', encoding="utf-8")

    bus = MagicMock()
    reg = DeviceRegistry()
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.discovery = DiscoveryConfig(lock_timeout_s=5.0)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(bus, reg, cfg)


class TestWebUiRoute:
    @pytest.mark.asyncio
    async def test_get_webui_returns_html(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            assert resp.status == 200
            assert resp.content_type == "text/html"
            body = await resp.text()
            assert "<html" in body

    @pytest.mark.asyncio
    async def test_webui_html_uses_relative_fetch_paths(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "api/v1/devices" in body
        assert "api/v1/modules" in body
        assert 'fetch("/api/v1' not in body
        assert "fetch('/api/v1" not in body
        # PATCH must use /api/v1/devices/{id}, never append after ?include_inactive=
        assert "DEVICE_BASE_URL" in body
        assert "DEVICES_URL + \"/\"" not in body
        assert "DEVICES_URL + '/'" not in body
        assert "DEVICE_BASE_URL + \"/\" + encodeURIComponent(device.id)" in body
        assert "buildMultiPressCell" in body
        assert '"multi_press"' in body
        assert "Multi-press" in body
        assert ">Refresh</button>" in body
        assert "Reload</button>" not in body
        assert "Search for new modules" in body
        assert "Installation &amp; network" in body
        assert "refreshModules" not in body
        assert "Refresh known modules" not in body
        assert '"/refresh"' in body or "/refresh" in body
        assert "module-action-btn" in body
        assert "Update" in body

    @pytest.mark.asyncio
    async def test_webui_route_does_not_shadow_existing_routes(
        self, tmp_path: Path
    ) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)
        app.router.add_get("/health", api._get_health)

        async with TestClient(TestServer(app)) as client:
            root_resp = await client.get("/")
            health_resp = await client.get("/health")

            assert root_resp.status == 200
            assert root_resp.content_type == "text/html"

            assert health_resp.status == 200
            assert health_resp.content_type == "application/json"
            body: dict[str, Any] = await health_resp.json()
            assert "status" in body

    @pytest.mark.asyncio
    async def test_webui_html_has_backup_restore_section(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "Backup" in body
        assert "api/v1/devices/export" in body
        assert "api/v1/devices/import" in body
        assert "api/v1/devices/reset" in body

    @pytest.mark.asyncio
    async def test_webui_input_module_uses_port_column_label(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "channelColumnLabel" in body
        assert "Physical input port on IP1100" in body
        assert '"Port"' in body or "'Port'" in body or "Port" in body

    @pytest.mark.asyncio
    async def test_webui_backup_restore_uses_relative_fetch_paths(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert '"/api/v1/devices/export"' not in body
        assert '"/api/v1/devices/import"' not in body
        assert '"/api/v1/devices/reset"' not in body

    @pytest.mark.asyncio
    async def test_webui_type_select_shows_icon_and_label(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "buildTypeCell" in body or 'el("select"' in body
        assert "type-select-native" in body
        assert "type-select-btn" not in body
        assert 'device.device_type === "dimmer"' in body

    @pytest.mark.asyncio
    async def test_webui_shows_hub_role_badge_and_status_fetch(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path)
        app = web.Application(middlewares=[api._api_error_middleware])
        app.router.add_get("/", api._get_webui)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/")
            body = await resp.text()

        assert "hub-role-badge" in body
        assert "hub-role-badge--slave" in body
        assert "buildHubRoleBadge" in body
        assert "api/v1/status" in body
        assert "HUB_ROLE_TOOLTIP" in body
        assert "Enable" not in body or "buildEnableAction" not in body
