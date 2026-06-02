"""Tests for gateway.installation (devices.json loading and validation)."""

import json
import tempfile
from pathlib import Path

import pytest

from gateway.device_registry import DeviceType
from gateway.installation import (
    ChannelConfig,
    InstallationConfig,
    InstallationError,
    ModuleConfig,
    make_entity_id,
)


@pytest.fixture
def valid_devices_json(tmp_path: Path) -> Path:
    data = {
        "modules": [
            {
                "name": "relay_module",
                "ip": "10.10.1.30",
                "type": "relay",
                "channels": [
                    {"ch": 0,  "legacy_id": 547, "description": "Keuken LED", "group": "Keuken"},
                    {"ch": 10, "legacy_id": 557, "description": "Patio", "group": "Buitenverlichting"},
                    {"ch": 16, "legacy_id": 563, "description": "Keuken LED 2"},
                    {"ch": 23, "legacy_id": 570, "description": "Keuken Ventilatie"},
                ],
            },
            {
                "name": "dimmer_module",
                "ip": "10.10.1.40",
                "type": "dimmer",
                "channels": [
                    {"ch": 0, "legacy_id": 571, "description": "Woonkamer Dimmer 1"},
                    {"ch": 1, "legacy_id": 572, "description": "Woonkamer Dimmer 2"},
                ],
            },
            {
                "name": "input_module",
                "ip": "10.10.1.50",
                "type": "input",
                "channels": [],
            },
        ]
    }
    p = tmp_path / "devices.json"
    p.write_text(json.dumps(data), encoding="utf-8")
    return p


class TestInstallationLoad:
    def test_load_valid(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        assert len(cfg.modules) == 3

        relay = cfg.module_by_ip("10.10.1.30")
        assert relay is not None
        assert relay.type == DeviceType.RELAY
        assert relay.name == "relay_module"
        assert len(relay.channels) == 4
        assert relay.channels[0].legacy_id == 547
        assert relay.channels[0].description == "Keuken LED"

        dimmer = cfg.module_by_ip("10.10.1.40")
        assert dimmer is not None
        assert dimmer.type == DeviceType.DIMMER
        assert len(dimmer.channels) == 2

        inp = cfg.module_by_ip("10.10.1.50")
        assert inp is not None
        assert inp.type == DeviceType.INPUT
        assert inp.channels == []

    def test_legacy_id_to_channel(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)

        entry = cfg.legacy_id_to_channel(547)
        assert entry == (DeviceType.RELAY, "10.10.1.30", 0)

        entry = cfg.legacy_id_to_channel(571)
        assert entry == (DeviceType.DIMMER, "10.10.1.40", 0)

        assert cfg.legacy_id_to_channel(9999) is None

    def test_entity_id_derivation(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        assert cfg.make_entity_id("10.10.1.30", "relay", 0) == "10.10.1.30:relay:0"
        assert cfg.make_entity_id("10.10.1.40", "dimmer", 1) == "10.10.1.40:dimmer:1"

    def test_module_level_make_entity_id(self) -> None:
        assert make_entity_id("10.10.1.30", "relay", 0) == "10.10.1.30:relay:0"
        assert make_entity_id("10.10.1.50", DeviceType.INPUT, 3) == "10.10.1.50:input:3"

    def test_legacy_id_lookup_still_works(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        result = cfg.legacy_id_to_channel(547)
        assert result is not None
        assert result[0].value == "relay"
        assert result[1] == "10.10.1.30"
        assert result[2] == 0

    def test_legacy_id_is_optional(self, tmp_path: Path) -> None:
        """devices.json zonder legacy_id veld moet laden zonder fout."""
        data = {"modules": [{"name": "r", "ip": "10.10.1.30", "type": "relay",
            "channels": [{"ch": 0, "description": "test"}]}]}
        p = tmp_path / "devices.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        assert cfg.legacy_id_to_channel(0) is None

    def test_field_modules(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        fm = cfg.field_modules()
        assert fm == {
            "relay": "10.10.1.30",
            "dimmer": "10.10.1.40",
            "input": "10.10.1.50",
        }

    def test_all_legacy_ids(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        ids = cfg.all_legacy_ids()
        assert ids == [547, 557, 563, 570, 571, 572]

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(InstallationError, match="not found"):
            InstallationConfig.load(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(InstallationError, match="not valid JSON"):
            InstallationConfig.load(p)

    def test_duplicate_legacy_id(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "channels": [{"ch": 0, "legacy_id": 547}]},
                {"ip": "10.10.1.40", "type": "dimmer", "channels": [{"ch": 0, "legacy_id": 547}]},
            ]
        }
        p = tmp_path / "dup.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Duplicate component id"):
            InstallationConfig.load(p)

    def test_duplicate_module_ip(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "channels": []},
                {"ip": "10.10.1.30", "type": "dimmer", "channels": []},
            ]
        }
        p = tmp_path / "dup_ip.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Duplicate module IP"):
            InstallationConfig.load(p)

    def test_unknown_module_type(self, tmp_path: Path) -> None:
        data = {"modules": [{"ip": "10.10.1.30", "type": "unknown_type", "channels": []}]}
        p = tmp_path / "bad_type.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Unknown module type"):
            InstallationConfig.load(p)

    def test_module_missing_ip(self, tmp_path: Path) -> None:
        data = {"modules": [{"type": "relay", "channels": []}]}
        p = tmp_path / "no_ip.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="missing 'ip'"):
            InstallationConfig.load(p)

    def test_channel_missing_ch_field(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "channels": [{"ch": "not_an_int", "legacy_id": 547}]}
            ]
        }
        p = tmp_path / "bad_ch.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="missing 'ch'"):
            InstallationConfig.load(p)


class TestInstallationConfig:
    def test_module_config_ip_decimal(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        relay = cfg.module_by_ip("10.10.1.30")
        assert relay is not None
        assert relay.ip_decimal == "30"

    def test_empty_modules_list(self, tmp_path: Path) -> None:
        data = {"modules": []}
        p = tmp_path / "empty.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        assert cfg.modules == []
        assert cfg.all_legacy_ids() == []
