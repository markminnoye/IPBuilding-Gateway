"""Tests for buttons_via_ha (wall buttons via Home Assistant)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest
from aiohttp import web
from aiohttp.test_utils import TestClient, TestServer

from gateway.config import GatewayConfig
from gateway.device_registry import ButtonEvent, DeviceKey, DeviceRegistry, DeviceType
from gateway.gateway_api import GatewayAPI
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache
from gateway.udp_bus import UDPBus


def test_buttons_via_ha_default() -> None:
    cfg = GatewayConfig()
    assert cfg.buttons_via_ha is True
    assert cfg.claims_input_modules is True
    assert cfg.hub_role == "slave"
    assert cfg.input_mode_label == "Slave"


def test_buttons_via_ha_false_maps_to_master_label() -> None:
    cfg = GatewayConfig(buttons_via_ha=False)
    assert cfg.claims_input_modules is False
    assert cfg.hub_role == "master"
    assert cfg.input_mode_label == "Master"


def test_from_env_buttons_via_ha(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({"modules": []}), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.setenv("GATEWAY_BUTTONS_VIA_HA", "0")
    monkeypatch.delenv("GATEWAY_HUB_ROLE", raising=False)
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()
    assert cfg.buttons_via_ha is False
    assert cfg.hub_role == "master"


def test_from_env_legacy_hub_role_master(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({"modules": []}), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.delenv("GATEWAY_BUTTONS_VIA_HA", raising=False)
    monkeypatch.setenv("GATEWAY_HUB_ROLE", "master")
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()
    assert cfg.buttons_via_ha is False
    assert cfg.hub_role == "master"


def test_from_env_invalid_legacy_hub_role_falls_back_to_true(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({"modules": []}), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.delenv("GATEWAY_BUTTONS_VIA_HA", raising=False)
    monkeypatch.setenv("GATEWAY_HUB_ROLE", "invalid")
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()
    assert cfg.buttons_via_ha is True
    assert cfg.hub_role == "slave"


def test_buttons_via_ha_env_overrides_legacy_hub_role(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path,
) -> None:
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({"modules": []}), encoding="utf-8")
    monkeypatch.setenv("GATEWAY_DEVICES_FILE", str(devices_file))
    monkeypatch.setenv("GATEWAY_BUTTONS_VIA_HA", "1")
    monkeypatch.setenv("GATEWAY_HUB_ROLE", "master")
    monkeypatch.delenv("GATEWAY_SIMULATED", raising=False)
    monkeypatch.delenv("GATEWAY_USE_ENV_DEFAULTS", raising=False)

    cfg = GatewayConfig.from_env()
    assert cfg.buttons_via_ha is True


@pytest.mark.asyncio
async def test_poll_loop_skips_input_when_buttons_via_ha_false() -> None:
    cfg = GatewayConfig(
        simulated_mode=True,
        poll_interval_s=0.05,
        actuator_poll_interval_s=0.05,
        buttons_via_ha=False,
    )
    bus = UDPBus(cfg)

    sent_commands: list[tuple[str, bytes]] = []
    original_send = bus.send_command

    async def tracking_send(module_ip: str, payload: bytes, port: int | None = None) -> None:
        sent_commands.append((module_ip, payload))
        await original_send(module_ip, payload, port)

    bus.send_command = tracking_send  # type: ignore[method-assign]
    await bus.start()
    await __import__("asyncio").sleep(0.15)
    await bus.stop()

    input_polls = [p for _, p in sent_commands if p == b"I0000"]
    relay_polls = [p for _, p in sent_commands if p == b"P0000"]
    assert relay_polls, "Relay polls should continue when buttons_via_ha is false"
    assert not input_polls, "Input polls must be skipped when buttons_via_ha is false"


def _installation_with_input() -> InstallationConfig:
    return InstallationConfig._parse({
        "modules": [
            {
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:11:22:33:44:55",
                "channels": [{"ch": 0, "name": "Light", "active": True}],
            },
            {
                "ip": "10.10.1.50",
                "type": "input",
                "mac": "00:11:22:33:44:66",
                "channels": [],
                "pushbuttons": [
                    {
                        "id": "2f8185190000df",
                        "name": "Hall",
                        "active": True,
                        "channel": 0,
                    },
                ],
            },
        ],
    })


def _make_api(tmp_path: Path, *, buttons_via_ha: bool = True) -> GatewayAPI:
    installation = _installation_with_input()
    devices_file = tmp_path / "devices.json"
    devices_file.write_text(json.dumps({"modules": []}), encoding="utf-8")

    bus = MagicMock()
    reg = DeviceRegistry()
    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.buttons_via_ha = buttons_via_ha
    cfg.claims_input_modules = buttons_via_ha
    cfg.hub_role = "slave" if buttons_via_ha else "master"
    cfg.input_mode_label = "Slave" if buttons_via_ha else "Master"
    cfg.metadata_timeout_s = 5
    cfg.reply_timeout_ms = 500
    cfg.discovery = MagicMock()
    cfg.discovery.lock_timeout_s = 5.0

    api = GatewayAPI(bus, reg, cfg)
    meta = ModuleMetadata(
        buttons=[{"id": "2f8185190000df", "descr": "Hall", "index": 0}],
    )
    cache = ModuleMetadataCache()
    cache._by_mac["00:11:22:33:44:66"] = meta
    api._meta_cache = cache
    return api


class TestButtonsViaHaGatewayAPI:
    @pytest.mark.asyncio
    async def test_status_includes_buttons_via_ha(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path, buttons_via_ha=False)
        app = web.Application()
        app.router.add_get("/api/v1/status", api._get_status)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/status")
            body = await resp.json()

        assert body["buttons_via_ha"] is False
        assert body["hub_role"] == "master"
        assert body["input_mode_label"] == "Master"

    @pytest.mark.asyncio
    async def test_devices_omit_pushbuttons_when_off(
        self, tmp_path: Path,
    ) -> None:
        api = _make_api(tmp_path, buttons_via_ha=False)
        app = web.Application()
        app.router.add_get("/api/v1/devices", api._get_devices)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices")
            body = await resp.json()

        device_types = {d.get("semantic_type") for d in body["devices"]}
        assert "button" not in device_types

    @pytest.mark.asyncio
    async def test_devices_include_pushbuttons_when_on(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path, buttons_via_ha=True)
        app = web.Application()
        app.router.add_get("/api/v1/devices", api._get_devices)

        async with TestClient(TestServer(app)) as client:
            resp = await client.get("/api/v1/devices")
            body = await resp.json()

        assert any(d.get("semantic_type") == "button" for d in body["devices"])

    def test_button_event_suppressed_when_off(self, tmp_path: Path) -> None:
        api = _make_api(tmp_path, buttons_via_ha=False)
        broadcasts: list[dict[str, Any]] = []

        async def capture(msg: dict[str, Any]) -> None:
            broadcasts.append(msg)

        api._broadcast = capture  # type: ignore[method-assign]

        key = DeviceKey(DeviceType.INPUT, "10.10.1.50", 0)
        api._on_button_event(key, ButtonEvent(id_hex="2f8185190000df", action="press"))
        assert not broadcasts
