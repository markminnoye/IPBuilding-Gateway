"""Unit tests for installation merge policy A."""

from __future__ import annotations

import pytest

from gateway.installation import InstallationConfig, InstallationError
from gateway.installation_merge import merge_installation


def _relay_module(ip: str, name: str, ch_name: str, *, ch: int = 0, device_id: str = "") -> dict:
    ch_entry = {
        "ch": ch,
        "name": ch_name,
        "room": "Keuken",
        "semantic_type": "light",
        "active": True,
        "max_watt": 60,
    }
    if device_id:
        ch_entry["id"] = device_id
    return {
        "name": name,
        "ip": ip,
        "type": "relay",
        "mac": "00:24:77:52:ac:be",
        "firmware": "5.0",
        "model": "IP0200PoE",
        "channels": [ch_entry],
    }


class TestMergePolicyA:
    def test_validate_rejects_unknown_type(self) -> None:
        merged = merge_installation(
            {"modules": []},
            {"modules": [{"ip": "10.10.1.30", "type": "unknown", "channels": []}]},
            "replace",
        )
        with pytest.raises(InstallationError, match="Unknown module type"):
            InstallationConfig._parse(merged)

    def test_merge_preserves_existing_name(self) -> None:
        current = {"modules": [_relay_module("10.10.1.30", "IP0200PoE", "Keuken LED")]}
        incoming = {
            "modules": [{
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [{
                    "ch": 0,
                    "name": "Imported name",
                    "room": "Imported room",
                    "active": False,
                }],
            }],
        }
        merged = merge_installation(current, incoming, "merge_modules")
        ch = merged["modules"][0]["channels"][0]
        assert ch["name"] == "Keuken LED"
        assert ch["room"] == "Keuken"
        assert ch["active"] is True

    def test_merge_new_channel_gets_import_name(self) -> None:
        current = {"modules": [_relay_module("10.10.1.30", "IP0200PoE", "Keuken LED")]}
        incoming = {
            "modules": [{
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 1, "name": "Patio", "room": "Buiten", "active": True}],
            }],
        }
        merged = merge_installation(current, incoming, "merge_modules")
        channels = merged["modules"][0]["channels"]
        assert len(channels) == 2
        new_ch = next(c for c in channels if c["ch"] == 1)
        assert new_ch["name"] == "Patio"
        assert new_ch["active"] is True

    def test_replace_without_buttons_preserves_buttons(self) -> None:
        current = {
            "modules": [],
            "buttons": [{"id": "abc123", "name": "Keuken", "hold_threshold_s": 1.5}],
        }
        incoming = {"modules": [_relay_module("10.10.1.30", "r", "x")]}
        merged = merge_installation(current, incoming, "replace")
        assert len(merged["buttons"]) == 1
        assert merged["buttons"][0]["id"] == "abc123"

    def test_replace_explicit_empty_buttons_clears(self) -> None:
        current = {
            "modules": [],
            "buttons": [{"id": "abc123", "name": "Keuken", "hold_threshold_s": 1.5}],
        }
        incoming = {"modules": [], "buttons": []}
        merged = merge_installation(current, incoming, "replace")
        assert merged["buttons"] == []

    def test_merge_preserves_custom_device_id(self) -> None:
        current = {
            "modules": [_relay_module(
                "10.10.1.30", "IP0200PoE", "Keuken LED", device_id="keuken-led",
            )],
        }
        incoming = {
            "modules": [{
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [{"ch": 0, "name": "Other", "id": "other-id"}],
            }],
        }
        merged = merge_installation(current, incoming, "merge_modules")
        ch = merged["modules"][0]["channels"][0]
        assert ch["id"] == "keuken-led"
        assert ch["name"] == "Keuken LED"

    def test_append_modules_skips_existing_mac(self) -> None:
        current = {"modules": [_relay_module("10.10.1.30", "IP0200PoE", "Keuken LED")]}
        incoming = {
            "modules": [
                _relay_module("10.10.1.40", "other", "x", ch=0),
            ],
        }
        incoming["modules"][0]["mac"] = "00:24:77:52:9e:a8"
        incoming["modules"][0]["ip"] = "10.10.1.40"
        merged = merge_installation(current, incoming, "append_modules")
        assert len(merged["modules"]) == 2

    def test_merge_updates_firmware(self) -> None:
        current = {"modules": [_relay_module("10.10.1.30", "IP0200PoE", "Keuken LED")]}
        incoming = {
            "modules": [{
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [],
            }],
        }
        merged = merge_installation(current, incoming, "merge_modules")
        assert merged["modules"][0]["firmware"] == "5.1"
