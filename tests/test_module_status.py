"""Tests for gateway.module_status — HTTP ``statuses`` parsing and hydration."""

from __future__ import annotations

import json
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.device_registry import DeviceKey, DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_status import (
    apply_statuses_to_registry,
    hydrate_registry_from_http,
    parse_statuses_payload,
)
from gateway.types import DeviceType


# ---------------------------------------------------------------------------
# parse_statuses_payload
# ---------------------------------------------------------------------------


class TestParseStatusesPayload:
    def test_relay_on_off(self) -> None:
        body = json.dumps([
            {"id": 0, "status": 1, "descr": "A"},
            {"id": 1, "status": 0, "descr": "B"},
        ])
        result = parse_statuses_payload(body, DeviceType.RELAY)
        assert result == {0: 1, 1: 0}

    def test_dimmer_levels(self) -> None:
        body = json.dumps([
            {"id": 0, "status": 30},
            {"id": 1, "status": 100},
            {"id": 2, "status": 0},
        ])
        result = parse_statuses_payload(body, DeviceType.DIMMER)
        assert result == {0: 30, 1: 100, 2: 0}

    def test_empty_string(self) -> None:
        assert parse_statuses_payload("", DeviceType.RELAY) == {}
        assert parse_statuses_payload("   ", DeviceType.RELAY) == {}

    def test_invalid_json_returns_empty(self) -> None:
        assert parse_statuses_payload("not json", DeviceType.RELAY) == {}

    def test_non_list_returns_empty(self) -> None:
        assert parse_statuses_payload("{}", DeviceType.RELAY) == {}
        assert parse_statuses_payload('"hello"', DeviceType.RELAY) == {}

    def test_skips_entries_without_id_or_status(self) -> None:
        body = json.dumps([
            {"id": 0, "status": 1},
            {"status": 1},  # missing id
            {"id": 2},  # missing status
            {"id": 3, "status": "bad"},  # bad status
        ])
        result = parse_statuses_payload(body, DeviceType.RELAY)
        assert result == {0: 1}

    def test_non_dict_entries_skipped(self) -> None:
        body = json.dumps([{"id": 0, "status": 1}, "garbage", 42])
        result = parse_statuses_payload(body, DeviceType.RELAY)
        assert result == {0: 1}


# ---------------------------------------------------------------------------
# apply_statuses_to_registry
# ---------------------------------------------------------------------------


class TestApplyStatusesToRegistry:
    def test_relay_applies_state_and_code(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        count = apply_statuses_to_registry(
            registry,
            "10.10.1.30",
            DeviceType.RELAY,
            {0: 1, 1: 0},
        )

        assert count == 2
        key0 = DeviceKey(DeviceType.RELAY, "10.10.1.30", 0)
        key1 = DeviceKey(DeviceType.RELAY, "10.10.1.30", 1)
        rs0 = registry.get_relay_state(key0)
        rs1 = registry.get_relay_state(key1)
        assert rs0 is not None
        assert rs0.state == "on"
        assert rs0.state_code == "0100"
        assert rs1 is not None
        assert rs1.state == "off"
        assert rs1.state_code == "0000"

    def test_dimmer_applies_level_clamped(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.40", DeviceType.DIMMER)

        count = apply_statuses_to_registry(
            registry,
            "10.10.1.40",
            DeviceType.DIMMER,
            {0: 30, 1: 0, 2: 250},
        )

        assert count == 3
        ds0 = registry.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0))
        ds2 = registry.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 2))
        assert ds0 is not None and ds0.level_percent == 30
        assert ds2 is not None and ds2.level_percent == 100  # clamped

    def test_seed_does_not_fire_callbacks(self) -> None:
        registry = DeviceRegistry()
        registry.register_module("10.10.1.30", DeviceType.RELAY)

        cb = MagicMock()
        registry.on_state_changed(cb)

        apply_statuses_to_registry(
            registry,
            "10.10.1.30",
            DeviceType.RELAY,
            {0: 1},
        )

        cb.assert_not_called()


# ---------------------------------------------------------------------------
# hydrate_registry_from_http
# ---------------------------------------------------------------------------


class TestHydrateRegistryFromHttp:
    def _make_installation(
        self, modules: list[dict[str, Any]]
    ) -> InstallationConfig:
        return InstallationConfig._parse({"modules": modules})

    @pytest.mark.asyncio
    async def test_no_targets_returns_zero(self) -> None:
        registry = DeviceRegistry()
        inst = self._make_installation([])
        result = await hydrate_registry_from_http(registry, inst, timeout=1.0)
        assert result == 0

    @pytest.mark.asyncio
    async def test_skips_input_modules(self) -> None:
        registry = DeviceRegistry()
        inst = self._make_installation([
            {
                "ip": "10.10.1.50", "type": "input",
                "mac": "00:24:77:52:ad:aa",
                "channels": [],
            },
        ])
        result = await hydrate_registry_from_http(registry, inst, timeout=1.0)
        assert result == 0

    @pytest.mark.asyncio
    async def test_seeds_relay_and_dimmer(self) -> None:
        registry = DeviceRegistry()
        inst = self._make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "channels": [],
            },
            {
                "ip": "10.10.1.40", "type": "dimmer",
                "mac": "00:24:77:52:9e:a8", "channels": [],
            },
        ])

        relay_body = json.dumps([{"id": 0, "status": 1}])
        dimmer_body = json.dumps([{"id": 0, "status": 50}])

        async def fake_http_get_text(ip, method, sess, timeout):
            return {"10.10.1.30": relay_body, "10.10.1.40": dimmer_body}.get(ip)

        with patch("gateway.module_status._http_get_text", side_effect=fake_http_get_text):
            result = await hydrate_registry_from_http(registry, inst, timeout=1.0)

        assert result == 2
        rs = registry.get_relay_state(DeviceKey(DeviceType.RELAY, "10.10.1.30", 0))
        ds = registry.get_dimmer_state(DeviceKey(DeviceType.DIMMER, "10.10.1.40", 0))
        assert rs is not None and rs.state == "on"
        assert ds is not None and ds.level_percent == 50

    @pytest.mark.asyncio
    async def test_http_failure_does_not_raise(self) -> None:
        registry = DeviceRegistry()
        inst = self._make_installation([
            {
                "ip": "10.10.1.30", "type": "relay",
                "mac": "00:24:77:52:ac:be", "channels": [],
            },
        ])

        async def fake_http_get_text(ip, method, sess, timeout):
            return None  # simulate network failure

        with patch("gateway.module_status._http_get_text", side_effect=fake_http_get_text):
            result = await hydrate_registry_from_http(registry, inst, timeout=1.0)

        assert result == 0
        # registry still empty
        rs = registry.get_relay_state(DeviceKey(DeviceType.RELAY, "10.10.1.30", 0))
        assert rs is None
