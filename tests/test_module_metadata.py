"""Tests for gateway.module_metadata — getSysSet/getButtons parsing and cache."""

from __future__ import annotations

import asyncio
from typing import Any
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from gateway.module_metadata import (
    ModuleMetadata,
    ModuleMetadataCache,
    _parse_get_sysset_body,
    normalize_button_hardware_id,
    extract_pushbutton_config,
    extract_pushbuttons_from_getbuttons,
)


class TestParseGetSysSet:
    def test_json_format(self) -> None:
        body = '{"dhcp": "0", "ip": "10.10.1.30", "subnet": "255.255.255.0", "gateway": "10.10.1.1", "mac": "0.36.119.82.172.190", "firm": "5.1"}'
        result = _parse_get_sysset_body(body)
        assert result["dhcp"] == "0"
        assert result["ip"] == "10.10.1.30"
        assert result["subnet"] == "255.255.255.0"
        assert result["gateway"] == "10.10.1.1"

    def test_key_value_format(self) -> None:
        body = "ip=10.10.1.40\r\nsubnet=255.255.255.0\r\ngateway=10.10.1.1\r\ndhcp=1\r\n"
        result = _parse_get_sysset_body(body)
        assert result["ip"] == "10.10.1.40"
        assert result["dhcp"] == "1"
        assert result["gateway"] == "10.10.1.1"

    def test_empty_body(self) -> None:
        assert _parse_get_sysset_body("") == {}
        assert _parse_get_sysset_body("   ") == {}

    def test_invalid_json_falls_back_to_kv(self) -> None:
        body = "not=json\nalso=valid"
        result = _parse_get_sysset_body(body)
        assert result["not"] == "json"
        assert result["also"] == "valid"


class TestModuleMetadataCache:
    def _make_installation(self, modules: list[dict[str, Any]]) -> MagicMock:
        from gateway.installation import InstallationConfig
        from gateway.types import DeviceType
        import json
        import tempfile
        from pathlib import Path

        # Build a real InstallationConfig using tmp devices.json
        raw = {"modules": modules}
        cfg = InstallationConfig._parse(raw)
        return cfg

    @pytest.mark.asyncio
    async def test_refresh_populates_cache(self) -> None:
        installation = self._make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []},
        ])

        sysset_response = '{"dhcp": "0", "ip": "10.10.1.30", "subnet": "255.255.255.0", "gateway": "10.10.1.1", "button": "0", "allow": ""}'

        async def fake_http_get(ip, method, sess, timeout):
            if method == "getSysSet":
                return sysset_response
            return None

        cache = ModuleMetadataCache()
        with patch("gateway.module_metadata._http_get_text", side_effect=fake_http_get):
            await cache.refresh(installation, timeout=1.0)

        meta = cache.get("00:24:77:52:ac:be")
        assert meta is not None
        assert meta.network["ip"] == "10.10.1.30"
        assert meta.network["dhcp"] == "0"
        assert meta.network["gateway"] == "10.10.1.1"
        assert meta.button == "0"
        assert meta.fetched_at is not None

    @pytest.mark.asyncio
    async def test_refresh_skips_module_without_mac(self) -> None:
        installation = self._make_installation([
            {"ip": "10.10.1.30", "type": "relay", "channels": []},  # no mac
        ])

        cache = ModuleMetadataCache()
        with patch("gateway.module_metadata._http_get_text", return_value="{}") as mock_http:
            await cache.refresh(installation, timeout=1.0)

        assert cache.all_macs() == []

    @pytest.mark.asyncio
    async def test_partial_failure_keeps_old_cache(self) -> None:
        installation = self._make_installation([
            {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []},
            {"ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8", "channels": []},
        ])

        call_count = 0

        async def fake_http(ip, method, sess, timeout):
            nonlocal call_count
            call_count += 1
            if ip == "10.10.1.30":
                return '{"dhcp": "0", "ip": "10.10.1.30", "subnet": "255.255.0.0", "gateway": "10.10.1.1"}'
            # Dimmer fails
            return None

        cache = ModuleMetadataCache()
        with patch("gateway.module_metadata._http_get_text", side_effect=fake_http):
            await cache.refresh(installation, timeout=1.0)

        # Relay should be cached
        relay_meta = cache.get("00:24:77:52:ac:be")
        assert relay_meta is not None
        assert relay_meta.network.get("ip") == "10.10.1.30"

        # Dimmer has no previous cache -- should be absent or empty
        dimmer_meta = cache.get("00:24:77:52:9e:a8")
        # No old entry; fresh cache will not have it
        assert dimmer_meta is None

    @pytest.mark.asyncio
    async def test_input_module_fetches_getbuttons(self) -> None:
        installation = self._make_installation([
            {"ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa", "channels": []},
        ])

        buttons_json = '[{"index": 0, "id": "2D2F8185190000DF", "descr": "Badkamer knop", "gr": "", "func1": null, "func2": null}]'

        async def fake_http(ip, method, sess, timeout):
            if method == "getSysSet":
                return '{"dhcp": "1", "ip": "10.10.1.50", "subnet": "255.255.0.0", "gateway": "10.10.1.1"}'
            if method == "getButtons":
                return buttons_json
            return None

        cache = ModuleMetadataCache()
        with patch("gateway.module_metadata._http_get_text", side_effect=fake_http), \
             patch("gateway.module_metadata._fetch_buttons", new=AsyncMock(return_value=[{"index": 0, "id": "2D2F8185190000DF"}])):
            await cache.refresh(installation, timeout=1.0)

        meta = cache.get("00:24:77:52:ad:aa")
        assert meta is not None
        assert meta.buttons is not None
        assert meta.buttons[0]["id"] == "2D2F8185190000DF"

    def test_get_returns_none_for_unknown_mac(self) -> None:
        cache = ModuleMetadataCache()
        assert cache.get("de:ad:be:ef:00:01") is None


class TestNormalizeButtonHardwareId:
    def test_strips_type_prefix_and_lowercases(self) -> None:
        assert normalize_button_hardware_id("2D2F8185190000DF") == "2f8185190000df"

    def test_already_wire_form_unchanged(self) -> None:
        assert normalize_button_hardware_id("2f8185190000df") == "2f8185190000df"

    def test_handles_whitespace(self) -> None:
        assert normalize_button_hardware_id("  2D2F8185190000DF\n") == "2f8185190000df"


class TestExtractPushbuttonConfig:
    def test_extracts_channel_from_index(self) -> None:
        raw = {
            "index": 1, "id": "2D2F8185190000DF", "descr": "Badkamer", "gr": "Badkamer",
            "func1": {"ip": 30, "ch": 12, "outType": 0, "action": 2},
            "func2": {"ip": 30, "ch": 9, "outType": 0, "action": 2},
        }
        btn = extract_pushbutton_config("00:24:77:52:ad:aa", raw)
        assert btn.channel == 1
        assert btn.id == "2f8185190000df"
        assert btn.module_id == "00:24:77:52:ad:aa"
        assert btn.name == "Badkamer"
        assert btn.room == "Badkamer"

    def test_missing_index_leaves_channel_none(self) -> None:
        raw = {"id": "2D2F8185190000DF", "descr": "Badkamer"}
        btn = extract_pushbutton_config("mac1", raw)
        assert btn.channel is None

    def test_missing_id_raises(self) -> None:
        with pytest.raises(ValueError, match="no 'id'"):
            extract_pushbutton_config("mac1", {"descr": "no id"})

    def test_hold_threshold_from_func2(self) -> None:
        raw = {"id": "abc", "func2": {"holdSeconds": 2.5}}
        btn = extract_pushbutton_config("mac1", raw)
        assert btn.hold_threshold_s == 2.5


class TestExtractPushbuttonsFromGetbuttons:
    def test_extracts_multiple_with_channel(self) -> None:
        raw = [
            {"index": 0, "id": "2DE341851900001F", "descr": "Badkamer"},
            {"index": 1, "id": "2DD68C5219000050", "descr": "Slaapkamer"},
        ]
        buttons = extract_pushbuttons_from_getbuttons("mac1", raw)
        assert len(buttons) == 2
        assert buttons[0].channel == 0
        assert buttons[1].channel == 1

    def test_skips_invalid_entries(self, caplog) -> None:
        raw = [{"descr": "no id, invalid"}, {"index": 5, "id": "2Dabc123", "descr": "valid"}]
        buttons = extract_pushbuttons_from_getbuttons("mac1", raw)
        assert len(buttons) == 1
        assert buttons[0].channel == 5
