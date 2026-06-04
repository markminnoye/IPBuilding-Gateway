"""Tests for gateway_api.py module endpoints and snapshot shape."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import MagicMock, patch

import pytest

from gateway.device_registry import DeviceRegistry, DeviceType
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache


def _make_installation(modules: list[dict[str, Any]]) -> InstallationConfig:
    return InstallationConfig._parse({"modules": modules})


def _make_registry(installation: InstallationConfig) -> DeviceRegistry:
    reg = DeviceRegistry()
    for mc in installation.modules:
        reg.register_module(mc.ip, mc.type)
    return reg


def _make_api(installation: InstallationConfig, cache: ModuleMetadataCache | None = None):
    """Return a GatewayAPI instance with mocked bus and config."""
    from gateway.gateway_api import GatewayAPI

    bus = MagicMock()
    reg = _make_registry(installation)
    cfg = MagicMock()
    cfg.installation = installation
    cfg.api_host = "127.0.0.1"
    cfg.api_port = 8080

    return GatewayAPI(bus, reg, cfg, metadata_cache=cache)


class TestBuildModuleList:
    def test_static_fields_present(self) -> None:
        inst = _make_installation([
            {
                "name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "model": "IP0200PoE",
                "firmware": "5.1", "channels": [],
            }
        ])
        api = _make_api(inst)
        modules = api._build_module_list()

        assert len(modules) == 1
        m = modules[0]
        assert m["id"] == "00:24:77:52:ac:be"
        assert m["mac"] == "00:24:77:52:ac:be"
        assert m["ip"] == "10.10.1.30"
        assert m["type"] == "relay"
        assert m["firmware"] == "5.1"
        assert m["model"] == "IP0200PoE"
        # No cache -- empty network
        assert m["network"] == {}

    def test_cached_network_fields_merged(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "channels": [],
            }
        ])
        cache = ModuleMetadataCache()
        meta = ModuleMetadata(
            network={"dhcp": "0", "ip": "10.10.1.30", "subnet": "255.255.255.0", "gateway": "10.10.1.1"},
            button="0",
            allow="",
            fetched_at="2026-06-03T18:00:00Z",
        )
        cache._by_mac["00:24:77:52:ac:be"] = meta

        api = _make_api(inst, cache=cache)
        modules = api._build_module_list()
        m = modules[0]
        assert m["network"]["ip"] == "10.10.1.30"
        assert m["network"]["dhcp"] == "0"
        assert m["button"] == "0"
        assert m["fetched_at"] == "2026-06-03T18:00:00Z"

    def test_empty_installation_returns_empty_list(self) -> None:
        inst = _make_installation([])
        api = _make_api(inst)
        assert api._build_module_list() == []


class TestBuildDeviceList:
    def test_firmware_not_in_device(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [{"ch": 0, "name": "Keuken LED", "room": "Keuken", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 1
        d = devices[0]
        assert "firmware" not in d, "firmware must not appear on device"

    def test_module_id_and_channel_on_device(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 5, "name": "Test", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        d = devices[0]
        assert d["module_id"] == "00:24:77:52:ac:be"
        assert d["module_ip"] == "10.10.1.30"
        assert d["channel"] == 5

    def test_inactive_channel_excluded(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "Active", "active": True, "max_watt": 60},
                    {"ch": 1, "name": "Inactive", "active": False, "max_watt": 60},
                ],
            }
        ])
        api = _make_api(inst)
        devices = api._build_device_list()
        assert len(devices) == 1
        assert devices[0]["channel"] == 0


class TestBuildSnapshot:
    def test_snapshot_has_type_and_both_arrays(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "Light", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        snapshot = api._build_snapshot()
        assert snapshot["type"] == "snapshot"
        assert "modules" in snapshot
        assert "devices" in snapshot
        assert isinstance(snapshot["modules"], list)
        assert isinstance(snapshot["devices"], list)

    def test_snapshot_module_ids_match_device_module_ids(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "L1", "active": True, "max_watt": 60}],
            }
        ])
        api = _make_api(inst)
        snapshot = api._build_snapshot()
        module_ids = {m["id"] for m in snapshot["modules"]}
        device_module_ids = {d["module_id"] for d in snapshot["devices"]}
        assert device_module_ids <= module_ids, "all device.module_id values must appear in modules list"


class TestLastSeenFields:
    """Module resource includes last_seen / last_seen_source runtime fields."""

    def test_module_list_includes_last_seen_when_set(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [],
            }
        ])
        # Set runtime-only fields on the ModuleConfig
        inst.modules[0].last_seen = "2026-06-04T18:00:00Z"
        inst.modules[0].last_seen_source = "arp"

        api = _make_api(inst)
        modules = api._build_module_list()

        assert len(modules) == 1
        assert modules[0]["last_seen"] == "2026-06-04T18:00:00Z"
        assert modules[0]["last_seen_source"] == "arp"

    def test_module_list_excludes_last_seen_when_not_set(self) -> None:
        inst = _make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [],
            }
        ])
        # last_seen is None by default
        api = _make_api(inst)
        modules = api._build_module_list()

        assert "last_seen" not in modules[0]
        assert "last_seen_source" not in modules[0]


class TestDiscoveryEndpoint:
    """POST /api/v1/discover endpoint (orchestrator must be set)."""

    @pytest.mark.asyncio
    async def test_discover_returns_503_when_no_orchestrator(self) -> None:
        inst = _make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}
        ])
        api = _make_api(inst)
        # No orchestrator set
        request = MagicMock()
        request.match_info = {}
        response = await api._post_discover(request)
        assert response.status == 503
