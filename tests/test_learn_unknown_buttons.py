"""Tests for learn-on-press unknown button persistence."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from unittest.mock import MagicMock

import pytest

from gateway import gateway_api
from gateway.device_registry import ButtonEvent, DeviceKey, DeviceRegistry, DeviceType
from gateway.installation import InstallationConfig


def _write_devices(path: Path, modules: list[dict[str, Any]]) -> None:
    path.write_text(json.dumps({"modules": modules}, indent=2) + "\n", encoding="utf-8")


def _make_api(tmp_path: Path, modules: list[dict[str, Any]]) -> gateway_api.GatewayAPI:
    devices_file = tmp_path / "devices.json"
    _write_devices(devices_file, modules)
    installation = InstallationConfig.load(str(devices_file))

    bus = MagicMock()
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)

    cfg = MagicMock()
    cfg.installation = installation
    cfg.devices_file = str(devices_file)
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080
    cfg.claims_input_modules = True
    cfg.buttons_via_ha = True
    cfg.multi_press = False
    cfg.multi_press_window_ms = 350
    cfg.discovery = MagicMock()
    cfg.discovery.lock_timeout_s = 5.0

    return gateway_api.GatewayAPI(bus, reg, cfg)


def _capturing_api(tmp_path: Path, modules: list[dict[str, Any]]) -> gateway_api.GatewayAPI:
    api = _make_api(tmp_path, modules)
    api._captured: list[dict[str, Any]] = []

    async def capture_broadcast(msg: dict[str, Any]) -> None:
        api._captured.append(msg)

    api._broadcast = capture_broadcast  # type: ignore[method-assign]
    return api


INPUT_MODULE = {
    "name": "IP1100PoE",
    "ip": "10.10.1.50",
    "type": "input",
    "mac": "00:24:77:52:ad:aa",
    "channels": [],
    "pushbuttons": [],
}


class TestLearnOnPress:
    @pytest.mark.asyncio
    async def test_unknown_press_persists_stub_and_emits_device_added(
        self, tmp_path: Path,
    ) -> None:
        api = _capturing_api(tmp_path, [INPUT_MODULE])
        key = DeviceKey(DeviceType.INPUT, "10.10.1.50", 0)
        btn_id = "2f8185190000df"

        api._on_button_event(key, ButtonEvent(id_hex=btn_id, action="press"))

        # Allow create_task(device_added) to run.
        import asyncio
        await asyncio.sleep(0)

        disk = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
        pbs = disk["modules"][0]["pushbuttons"]
        assert len(pbs) == 1
        assert pbs[0]["id"] == btn_id
        assert pbs[0]["name"] == ""
        assert pbs[0]["room"] == ""
        assert pbs[0]["active"] is True

        assert api._cfg.installation.pushbutton_by_id(btn_id) is not None

        types = [m["type"] for m in api._captured]
        assert "device_added" in types
        assert "button_event" in types
        assert types.index("device_added") < types.index("button_event")

        added = next(m for m in api._captured if m["type"] == "device_added")
        assert added["semantic_type"] == "button"
        assert added["id"] == btn_id
        assert added["module_ip"] == "10.10.1.50"
        assert added["active"] is True
        assert added["name"] == ""

        press = next(m for m in api._captured if m["type"] == "button_event")
        assert press["action"] == "press"
        assert press["id"] == btn_id

    @pytest.mark.asyncio
    async def test_second_press_does_not_duplicate_stub(self, tmp_path: Path) -> None:
        api = _capturing_api(tmp_path, [INPUT_MODULE])
        key = DeviceKey(DeviceType.INPUT, "10.10.1.50", 0)
        btn_id = "2f8185190000df"

        api._on_button_event(key, ButtonEvent(id_hex=btn_id, action="press"))
        api._on_button_event(key, ButtonEvent(id_hex=btn_id, action="release"))
        api._on_button_event(key, ButtonEvent(id_hex=btn_id, action="press"))

        import asyncio
        await asyncio.sleep(0)

        disk = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
        assert len(disk["modules"][0]["pushbuttons"]) == 1
        assert sum(1 for m in api._captured if m["type"] == "device_added") == 1

    @pytest.mark.asyncio
    async def test_unknown_module_does_not_learn(self, tmp_path: Path) -> None:
        api = _capturing_api(tmp_path, [INPUT_MODULE])
        key = DeviceKey(DeviceType.INPUT, "10.10.1.99", 0)

        api._on_button_event(
            key, ButtonEvent(id_hex="aaaaaaaaaaaaaa", action="press"),
        )
        import asyncio
        await asyncio.sleep(0)

        disk = json.loads((tmp_path / "devices.json").read_text(encoding="utf-8"))
        assert disk["modules"][0]["pushbuttons"] == []
        assert not any(m["type"] == "device_added" for m in api._captured)
        # button_event still fires (transport), even if not learned
        assert any(m.get("action") == "press" for m in api._captured)
