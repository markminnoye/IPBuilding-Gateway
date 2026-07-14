"""Tests for GET/POST /api/v1/devices/export|import|reset (backup & restore)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

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
    app.router.add_post("/api/v1/devices/import", api._post_devices_import)
    app.router.add_post("/api/v1/devices/reset", api._post_devices_reset)
    app.router.add_post("/api/v1/modules/refresh", api._post_modules_refresh)
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


class TestExportAfterRefresh:
    @pytest.mark.asyncio
    async def test_export_includes_pushbuttons_after_modules_refresh(
        self, tmp_path: Path,
    ) -> None:
        from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache

        installation = _make_installation([
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "pushbuttons": [],
            }
        ])
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, installation)

        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            network={},
            buttons=[
                {
                    "index": 1,
                    "id": "2D2F8185190000DF",
                    "descr": "Badkamer",
                    "gr": "Badkamer",
                }
            ],
        )

        api = _make_api(installation, devices_file, metadata_cache=cache)
        api._meta_cache.refresh = AsyncMock(return_value=None)  # type: ignore[assignment]
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            refresh_resp = await client.post("/api/v1/modules/refresh")
            assert refresh_resp.status == 200

            export_resp = await client.get("/api/v1/devices/export")
            assert export_resp.status == 200
            exported = json.loads(await export_resp.read())

        input_module = next(m for m in exported["modules"] if m["type"] == "input")
        assert len(input_module["pushbuttons"]) == 1
        assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
        assert "channels" not in input_module


class TestImport:
    @pytest.mark.asyncio
    async def test_import_valid_document_replaces_file_and_reloads(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        new_doc = {
            "modules": [
                {
                    "name": "IP0200PoE",
                    "ip": "10.10.1.40",
                    "type": "relay",
                    "mac": "00:24:77:52:ac:cf",
                    "channels": [
                        {"ch": 0, "name": "Nieuwe lamp", "room": "Bureau",
                         "semantic_type": "light", "active": True, "max_watt": 20},
                        {"ch": 1, "name": "Extra", "room": "Bureau",
                         "semantic_type": "switch", "active": True, "max_watt": 0},
                    ],
                }
            ]
        }

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps(new_doc),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True
            assert body["modules"] == 1
            assert body["channels"] == 2
            assert body["pushbuttons"] == 0

        on_disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert on_disk == new_doc
        assert api._cfg.installation.module_by_ip("10.10.1.40") is not None
        assert api._cfg.installation.module_by_ip("10.10.1.30") is None

    @pytest.mark.asyncio
    async def test_import_empty_modules_is_valid(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["modules"] == 0

    @pytest.mark.asyncio
    async def test_import_invalid_json_returns_400(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        original_bytes = devices_file.read_bytes()
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data="{not valid json",
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_json"

        assert devices_file.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_import_duplicate_mac_returns_400_and_leaves_file_unchanged(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        original_bytes = devices_file.read_bytes()
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        bad_doc = {
            "modules": [
                {"name": "A", "ip": "10.10.1.30", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
                {"name": "B", "ip": "10.10.1.31", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
            ]
        }

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps(bad_doc),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_devices_file"

        assert devices_file.read_bytes() == original_bytes

    @pytest.mark.asyncio
    async def test_import_old_flat_buttons_format_returns_400(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": [], "buttons": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 400
            body = await resp.json()
            assert body["error"] == "invalid_devices_file"

    @pytest.mark.asyncio
    async def test_import_clears_stale_metadata_cache(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache

        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ac:be"] = ModuleMetadata(
            network={}, button="", allow="", buttons=None, fetched_at=None
        )
        api = _make_api(sample_installation, devices_file, metadata_cache=cache)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post(
                "/api/v1/devices/import",
                data=json.dumps({"modules": []}),
                headers={"Content-Type": "application/json"},
            )
            assert resp.status == 200

        assert cache.all_macs() == []


class TestReset:
    @pytest.mark.asyncio
    async def test_reset_empties_devices_file(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        api = _make_api(sample_installation, devices_file)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/v1/devices/reset")
            assert resp.status == 200
            body = await resp.json()
            assert body["ok"] is True

        on_disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert on_disk == {"modules": []}
        assert api._cfg.installation.modules == []

    @pytest.mark.asyncio
    async def test_reset_clears_metadata_cache(
        self, tmp_path: Path, sample_installation: InstallationConfig
    ) -> None:
        from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache

        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, sample_installation)
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ac:be"] = ModuleMetadata(
            network={}, button="", allow="", buttons=None, fetched_at=None
        )
        api = _make_api(sample_installation, devices_file, metadata_cache=cache)
        app = _app_with_routes(api)

        async with TestClient(TestServer(app)) as client:
            resp = await client.post("/api/v1/devices/reset")
            assert resp.status == 200

        assert cache.all_macs() == []
