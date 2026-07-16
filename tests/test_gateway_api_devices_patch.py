"""Tests for PATCH /api/v1/devices/{device_id}."""

from __future__ import annotations

import asyncio
import fcntl
import json
import os
from pathlib import Path
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway import gateway_api
from gateway.auto_discovery import DiscoveryConfig
from gateway.device_config import DeviceConfigError
from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache


def _make_installation(modules: list[dict[str, Any]] | None = None) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules or []})


def _write_devices_file(path: Path, installation: InstallationConfig) -> None:
    from gateway.device_config import installation_to_raw_dict

    path.write_text(json.dumps(installation_to_raw_dict(installation), indent=2), encoding="utf-8")


def _make_api(
    installation: InstallationConfig,
    devices_file: Path,
    discovery: DiscoveryConfig | None = None,
    metadata_cache: gateway_api.ModuleMetadataCache | None = None,
) -> gateway_api.GatewayAPI:
    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.discovery = discovery or DiscoveryConfig(lock_timeout_s=5.0)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.metadata_timeout_s = 5
    return gateway_api.GatewayAPI(
        bus, reg, cfg, metadata_cache=metadata_cache
    )


@pytest.fixture
def channel_installation() -> InstallationConfig:
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


@pytest.fixture
def dimmer_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP0300PoE",
            "ip": "10.10.1.40",
            "type": "dimmer",
            "mac": "00:24:77:52:9e:a8",
            "channels": [
                {
                    "ch": 0,
                    "name": "Living",
                    "room": "Gelijkvloers",
                    "semantic_type": "light",
                    "active": True,
                    "max_watt": 200,
                }
            ],
        }
    ])


@pytest.fixture
def pushbutton_installation() -> InstallationConfig:
    return _make_installation([
        {
            "name": "IP1100PoE",
            "ip": "10.10.1.50",
            "type": "input",
            "mac": "00:24:77:52:ad:aa",
            "pushbuttons": [
                {
                    "id": "2f8185190000df",
                    "channel": 1,
                    "name": "Badkamer knop",
                    "room": "1e verdieping",
                    "active": True,
                    "hold_threshold_s": 1.5,
                }
            ],
        }
    ])


class TestPatchDeviceHandler:
    @pytest.mark.asyncio
    async def test_patch_channel_success(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Eetkamer", "max_watt": 40})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with patch.object(api, "_broadcast", new_callable=AsyncMock) as mock_broadcast:
            response = await api._patch_device(request)

        assert response.status == 200
        body = json.loads(response.body)
        assert body["room"] == "Eetkamer"
        assert body["max_watt"] == 40

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert disk["modules"][0]["channels"][0]["room"] == "Eetkamer"
        assert disk["modules"][0]["channels"][0]["max_watt"] == 40
        assert api._cfg.installation.module_by_ip("10.10.1.30").channels[0].room == "Eetkamer"
        mock_broadcast.assert_called_once()

    @pytest.mark.asyncio
    async def test_patch_pushbutton_success(
        self, tmp_path: Path, pushbutton_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, pushbutton_installation)
        api = _make_api(pushbutton_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"name": "Douche knop", "active": False})
        request.match_info = {"device_id": "2f8185190000df"}

        response = await api._patch_device(request)
        body = json.loads(response.body)

        assert response.status == 200
        assert body["name"] == "Douche knop"
        assert body["active"] is False
        assert body["semantic_type"] == "button"
        assert body["channel"] == 1
        assert body["multi_press"] is False

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        input_module = next(m for m in disk["modules"] if m["type"] == "input")
        assert input_module["pushbuttons"][0]["name"] == "Douche knop"
        assert input_module["pushbuttons"][0]["active"] is False

    @pytest.mark.asyncio
    async def test_patch_pushbutton_multi_press(
        self, tmp_path: Path, pushbutton_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, pushbutton_installation)
        api = _make_api(pushbutton_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"multi_press": True})
        request.match_info = {"device_id": "2f8185190000df"}

        response = await api._patch_device(request)
        body = json.loads(response.body)

        assert response.status == 200
        assert body["multi_press"] is True
        assert (
            api._cfg.installation.pushbutton_by_id("2f8185190000df").multi_press
            is True
        )

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        input_module = next(m for m in disk["modules"] if m["type"] == "input")
        assert input_module["pushbuttons"][0]["multi_press"] is True

    @pytest.mark.asyncio
    async def test_patch_preserves_pushbuttons_when_updating_other_module_channel(
        self, tmp_path: Path
    ) -> None:
        combined = _make_installation([
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
            },
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "pushbuttons": [
                    {"id": "2f8185190000df", "name": "Badkamer knop", "room": "1e verdieping", "active": True}
                ],
            },
        ])
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, combined)
        api = _make_api(combined, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Hal"})
        request.match_info = {"device_id": "10.10.1.30-0"}
        await api._patch_device(request)

        disk = json.loads(devices_file.read_text(encoding="utf-8"))
        assert "buttons" not in disk
        input_module = next(m for m in disk["modules"] if m["type"] == "input")
        assert len(input_module["pushbuttons"]) == 1
        assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"

    @pytest.mark.asyncio
    async def test_patch_invalid_json(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(side_effect=ValueError("bad json"))
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "invalid_json"

    @pytest.mark.asyncio
    async def test_patch_unknown_field(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"ip": "10.10.1.99"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "unknown_field"

    @pytest.mark.asyncio
    async def test_patch_bad_semantic_type(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"semantic_type": "sensor"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "validation"

    @pytest.mark.asyncio
    async def test_patch_dimmer_rejects_non_light_semantic_type(
        self, tmp_path: Path, dimmer_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, dimmer_installation)
        api = _make_api(dimmer_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"semantic_type": "fan"})
        request.match_info = {"device_id": "10.10.1.40-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "validation"
        assert "dimmer" in exc.value.message

    @pytest.mark.asyncio
    async def test_patch_dimmer_room_without_semantic_type(
        self, tmp_path: Path, dimmer_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, dimmer_installation)
        api = _make_api(dimmer_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Salon"})
        request.match_info = {"device_id": "10.10.1.40-0"}

        resp = await api._patch_device(request)
        assert resp.status == 200
        body = json.loads(resp.text)
        assert body["room"] == "Salon"
        assert body["semantic_type"] == "light"

    @pytest.mark.asyncio
    async def test_patch_device_not_found(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "X"})
        request.match_info = {"device_id": "10.10.1.99-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_patch_write_locked(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file, DiscoveryConfig(lock_timeout_s=0.3))

        lock_file = tmp_path / "devices.json.lock"
        lock_fd = os.open(str(lock_file), os.O_RDONLY | os.O_CREAT, 0o644)
        try:
            fcntl.flock(lock_fd, fcntl.LOCK_EX)

            request = MagicMock()
            request.json = AsyncMock(return_value={"room": "Blocked"})
            request.match_info = {"device_id": "10.10.1.30-0"}

            with pytest.raises(gateway_api.ApiError) as exc:
                await api._patch_device(request)
            assert exc.value.status == 503
            assert exc.value.code == "write_locked"
        finally:
            fcntl.flock(lock_fd, fcntl.LOCK_UN)
            os.close(lock_fd)

    @pytest.mark.asyncio
    async def test_patch_route_via_test_client(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)
        api._app = web.Application(middlewares=[api._api_error_middleware])
        api._app.router.add_patch("/api/v1/devices/{device_id}", api._patch_device)

        async with TestClient(TestServer(api._app)) as client:
            resp = await client.patch(
                "/api/v1/devices/10.10.1.30-0",
                json={"room": "Via HTTP"},
            )
            assert resp.status == 200
            body = await resp.json()
            assert body["room"] == "Via HTTP"
            assert body["schema_version"] == 2


class TestPatchWsBroadcast:
    @pytest.mark.asyncio
    async def test_patch_broadcasts_snapshot(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        broadcast_called = asyncio.Event()
        original_broadcast = api._broadcast

        async def _capture_broadcast(msg: dict) -> None:
            if msg.get("type") == "snapshot":
                broadcast_called.set()
            await original_broadcast(msg)

        with patch.object(api, "_broadcast", side_effect=_capture_broadcast):
            request = MagicMock()
            request.json = AsyncMock(return_value={"room": "WS test"})
            request.match_info = {"device_id": "10.10.1.30-0"}
            await api._patch_device(request)

        await asyncio.wait_for(broadcast_called.wait(), timeout=1.0)


class TestPatchReviewFixes:
    @pytest.mark.asyncio
    async def test_patch_empty_body_rejected(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with pytest.raises(gateway_api.ApiError) as exc:
            await api._patch_device(request)
        assert exc.value.status == 400
        assert exc.value.code == "empty_body"

    @pytest.mark.asyncio
    async def test_patch_device_not_found_during_write(
        self, tmp_path: Path, channel_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, channel_installation)
        api = _make_api(channel_installation, devices_file)

        request = MagicMock()
        request.json = AsyncMock(return_value={"room": "Gone"})
        request.match_info = {"device_id": "10.10.1.30-0"}

        with patch.object(
            api._writer,
            "read_modify_write",
            side_effect=DeviceConfigError(
                "device_not_found",
                "Channel 0 not found on module 10.10.1.30",
                {"module_ip": "10.10.1.30", "channel": 0},
            ),
        ):
            with pytest.raises(gateway_api.ApiError) as exc:
                await api._patch_device(request)
        assert exc.value.status == 404
        assert exc.value.code == "device_not_found"

    @pytest.mark.asyncio
    async def test_patch_pushbutton_response_overlays_installation_over_meta_cache(
        self, tmp_path: Path, pushbutton_installation: InstallationConfig
    ) -> None:
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, pushbutton_installation)
        mac = "00:24:77:52:ad:aa"
        meta_cache = ModuleMetadataCache()
        meta_cache._by_mac[mac] = ModuleMetadata(
            buttons=[
                {
                    "id": "2D2F8185190000DF",
                    "descr": "Stale HTTP name",
                    "gr": "Stale room",
                }
            ]
        )
        api = _make_api(pushbutton_installation, devices_file, metadata_cache=meta_cache)

        request = MagicMock()
        request.json = AsyncMock(
            return_value={"name": "Patched name", "room": "Patched room"}
        )
        request.match_info = {"device_id": "2f8185190000df"}

        with patch.object(api, "_broadcast", new_callable=AsyncMock):
            response = await api._patch_device(request)

        body = json.loads(response.body)
        assert body["name"] == "Patched name"
        assert body["room"] == "Patched room"
        assert body["schema_version"] == 2


class TestUnconfiguredPushbuttonHasChannelFromMeta:
    @pytest.mark.asyncio
    async def test_unconfigured_pushbutton_channel_from_index(self, tmp_path: Path) -> None:
        """A pushbutton only known via getButtons metadata still surfaces 'channel' (from 'index')."""
        installation = _make_installation([
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"}
        ])
        devices_file = tmp_path / "devices.json"
        _write_devices_file(devices_file, installation)
        mac = "00:24:77:52:ad:aa"
        meta_cache = ModuleMetadataCache()
        meta_cache._by_mac[mac] = ModuleMetadata(
            buttons=[{"id": "2D2F8185190000DF", "index": 3, "descr": "Bureau L", "gr": "Bureau"}]
        )
        api = _make_api(installation, devices_file, metadata_cache=meta_cache)

        devices = api._build_device_list()
        pushbutton = next(d for d in devices if d["id"] == "2f8185190000df")
        assert pushbutton["channel"] == 3
        # 'active' is intentionally omitted for unconfigured input-buttons
        # (see test_gateway_api_modules.py::test_input_button_omits_active_field) —
        # the companion treats a missing key as enabled-by-default via
        # device.get("active", True).
        assert "active" not in pushbutton
