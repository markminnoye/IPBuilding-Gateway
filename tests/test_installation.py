"""Tests for gateway.installation (devices.json loading and validation)."""

import json
import tempfile
from pathlib import Path

import pytest

from gateway.device_registry import DeviceType
from gateway.gateway_api import _resolve_entity_id
from gateway.installation import (
    ChannelConfig,
    DetectorConfig,
    InstallationConfig,
    InstallationError,
    ModuleConfig,
    PushbuttonConfig,
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
                    {"ch": 0,  "ipbox_id": 547, "description": "Keuken LED", "group": "Keuken"},
                    {"ch": 10, "ipbox_id": 557, "description": "Patio", "group": "Buitenverlichting"},
                    {"ch": 16, "ipbox_id": 563, "description": "Keuken LED 2"},
                    {"ch": 23, "ipbox_id": 570, "description": "Keuken Ventilatie"},
                ],
            },
            {
                "name": "dimmer_module",
                "ip": "10.10.1.40",
                "type": "dimmer",
                "channels": [
                    {"ch": 0, "ipbox_id": 571, "description": "Woonkamer Dimmer 1"},
                    {"ch": 1, "ipbox_id": 572, "description": "Woonkamer Dimmer 2"},
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
        assert relay.channels[0].ipbox_id == 547
        assert relay.channels[0].description == "Keuken LED"

        dimmer = cfg.module_by_ip("10.10.1.40")
        assert dimmer is not None
        assert dimmer.type == DeviceType.DIMMER
        assert len(dimmer.channels) == 2

        inp = cfg.module_by_ip("10.10.1.50")
        assert inp is not None
        assert inp.type == DeviceType.INPUT
        assert inp.channels == []

    def test_ipbox_id_to_channel(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)

        entry = cfg.ipbox_id_to_channel(547)
        assert entry == (DeviceType.RELAY, "10.10.1.30", 0)

        entry = cfg.ipbox_id_to_channel(571)
        assert entry == (DeviceType.DIMMER, "10.10.1.40", 0)

        assert cfg.ipbox_id_to_channel(9999) is None

    def test_entity_id_derivation(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        assert cfg.make_entity_id("10.10.1.30", 0) == "10.10.1.30-0"
        assert cfg.make_entity_id("10.10.1.40", 1) == "10.10.1.40-1"

    def test_module_level_make_entity_id(self) -> None:
        assert make_entity_id("10.10.1.30", 0) == "10.10.1.30-0"
        assert make_entity_id("10.10.1.50", 3) == "10.10.1.50-3"

    def test_ipbox_id_lookup_still_works(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        result = cfg.ipbox_id_to_channel(547)
        assert result is not None
        assert result[0].value == "relay"
        assert result[1] == "10.10.1.30"
        assert result[2] == 0

    def test_ipbox_id_is_optional(self, tmp_path: Path) -> None:
        """devices.json zonder ipbox_id veld moet laden zonder fout."""
        data = {"modules": [{"name": "r", "ip": "10.10.1.30", "type": "relay",
            "channels": [{"ch": 0, "description": "test"}]}]}
        p = tmp_path / "devices.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        assert cfg.ipbox_id_to_channel(0) is None

    def test_dimmer_channel_semantic_type_normalized_to_light(self) -> None:
        cfg = InstallationConfig._parse({
            "modules": [{
                "name": "IP0300PoE",
                "ip": "10.10.1.40",
                "type": "dimmer",
                "mac": "00:24:77:52:9e:a8",
                "channels": [{
                    "ch": 0,
                    "name": "Living",
                    "semantic_type": "fan",
                }],
            }],
        })
        dimmer = cfg.module_by_ip("10.10.1.40")
        assert dimmer is not None
        assert dimmer.channels[0].semantic_type == "light"

    def test_field_modules(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        fm = cfg.field_modules()
        assert fm == {
            "relay": "10.10.1.30",
            "dimmer": "10.10.1.40",
            "input": "10.10.1.50",
        }

    def test_all_ipbox_ids(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        ids = cfg.all_ipbox_ids()
        assert ids == [547, 557, 563, 570, 571, 572]

    def test_missing_file(self, tmp_path: Path) -> None:
        with pytest.raises(InstallationError, match="not found"):
            InstallationConfig.load(tmp_path / "nonexistent.json")

    def test_invalid_json(self, tmp_path: Path) -> None:
        p = tmp_path / "bad.json"
        p.write_text("{not json", encoding="utf-8")
        with pytest.raises(InstallationError, match="not valid JSON"):
            InstallationConfig.load(p)

    def test_duplicate_ipbox_id(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "channels": [{"ch": 0, "ipbox_id": 547}]},
                {"ip": "10.10.1.40", "type": "dimmer", "channels": [{"ch": 0, "ipbox_id": 547}]},
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
                {"ip": "10.10.1.30", "type": "relay", "channels": [{"ch": "not_an_int", "ipbox_id": 547}]}
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
        assert cfg.all_ipbox_ids() == []

    def test_mac_is_parsed(self, tmp_path: Path) -> None:
        """MAC is normalised and stored on ModuleConfig."""
        data = {
            "modules": [
                {
                    "name": "relay",
                    "ip": "10.10.1.30",
                    "type": "relay",
                    "mac": "0:24:77:52:ac:be",
                    "channels": [{"ch": 0}],
                }
            ]
        }
        p = tmp_path / "mac.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        relay = cfg.module_by_ip("10.10.1.30")
        assert relay is not None
        assert relay.mac == "00:24:77:52:ac:be"
        assert relay.module_id == "00:24:77:52:ac:be"

    def test_mac_normalisation_formats(self, tmp_path: Path) -> None:
        """Various MAC formats are normalised to lowercase colon."""
        cases = [
            ("0:24:77:52:ac:be", "00:24:77:52:ac:be"),
            ("00:24:77:52:ac:be", "00:24:77:52:ac:be"),
            ("00-24-77-52-ac-be", "00:24:77:52:ac:be"),
            ("0.24.77.52.ac.be", "00:24:77:52:ac:be"),
        ]
        for raw, expected in cases:
            data = {
                "modules": [
                    {"ip": "10.10.1.30", "type": "relay", "mac": raw, "channels": [{"ch": 0}]}
                ]
            }
            p = tmp_path / f"mac_{hash(raw)}.json"
            p.write_text(json.dumps(data), encoding="utf-8")
            cfg = InstallationConfig.load(p)
            assert cfg.module_by_ip("10.10.1.30").mac == expected, f"failed for {raw}"

    def test_module_by_mac(self, tmp_path: Path) -> None:
        """module_by_mac() returns ModuleConfig for a normalised MAC."""
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": [{"ch": 0}]},
                {"ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:9e:a8", "channels": [{"ch": 0}]},
            ]
        }
        p = tmp_path / "mac.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)

        relay = cfg.module_by_mac("00:24:77:52:ac:be")
        assert relay is not None
        assert relay.ip == "10.10.1.30"
        assert relay.type == DeviceType.RELAY

        dimmer = cfg.module_by_mac("00:24:77:52:9e:a8")
        assert dimmer is not None
        assert dimmer.ip == "10.10.1.40"

        assert cfg.module_by_mac("nonexistent") is None

    def test_duplicate_module_mac_rejected(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": [{"ch": 0}]},
                {"ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:ac:be", "channels": [{"ch": 0}]},
            ]
        }
        p = tmp_path / "dup_mac.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Duplicate module MAC"):
            InstallationConfig.load(p)

    def test_module_id_property(self, tmp_path: Path) -> None:
        """module_id property is an alias for mac."""
        data = {"modules": [{"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": [{"ch": 0}]}]}
        p = tmp_path / "mid.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        mc = cfg.module_by_ip("10.10.1.30")
        assert mc.module_id == mc.mac == "00:24:77:52:ac:be"


class TestResolveEntityId:
    """Tests for _resolve_entity_id — the server-side entity_id resolver."""

    def test_valid_relay_entity_id(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        result = _resolve_entity_id("10.10.1.30-0", cfg)
        assert result is not None
        module_ip, dtype, channel = result
        assert module_ip == "10.10.1.30"
        assert dtype == DeviceType.RELAY
        assert channel == 0

    def test_valid_dimmer_entity_id(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        result = _resolve_entity_id("10.10.1.40-1", cfg)
        assert result is not None
        module_ip, dtype, channel = result
        assert module_ip == "10.10.1.40"
        assert dtype == DeviceType.DIMMER
        assert channel == 1

    def test_unknown_device_id_rejected(self, valid_devices_json: Path) -> None:
        cfg = InstallationConfig.load(valid_devices_json)
        assert _resolve_entity_id("10.10.1.99-0", cfg) is None

    def test_none_installation_rejected(self) -> None:
        assert _resolve_entity_id("10.10.1.30-0", None) is None


class TestPushbuttonConfig:
    def test_to_dict_excludes_module_id(self) -> None:
        btn = PushbuttonConfig(
            id="2f8185190000df",
            module_id="00:24:77:52:ad:aa",
            channel=1,
            name="Badkamer knop",
            room="1e verdieping",
            active=True,
            hold_threshold_s=1.5,
        )
        d = btn.to_dict()
        assert "module_id" not in d
        assert d == {
            "id": "2f8185190000df",
            "channel": 1,
            "name": "Badkamer knop",
            "room": "1e verdieping",
            "active": True,
            "hold_threshold_s": 1.5,
        }

    def test_to_dict_omits_channel_when_none(self) -> None:
        btn = PushbuttonConfig(id="abc")
        d = btn.to_dict()
        assert "channel" not in d

    def test_from_dict_takes_module_id_as_argument(self) -> None:
        raw = {
            "id": "2f8185190000df",
            "channel": 1,
            "name": "Badkamer knop",
            "room": "1e verdieping",
            "active": True,
            "hold_threshold_s": 1.5,
        }
        btn = PushbuttonConfig.from_dict(raw, module_id="00:24:77:52:ad:aa")
        assert btn.module_id == "00:24:77:52:ad:aa"
        assert btn.channel == 1
        assert btn.name == "Badkamer knop"

    def test_from_dict_defaults_channel_to_none(self) -> None:
        btn = PushbuttonConfig.from_dict({"id": "abc"}, module_id="mac1")
        assert btn.channel is None


class TestDetectorConfig:
    def test_to_dict_round_trip(self) -> None:
        det = DetectorConfig(id="det1", name="Voordeur", room="Inkomhal", active=False)
        d = det.to_dict()
        assert d == {"id": "det1", "name": "Voordeur", "room": "Inkomhal", "active": False}
        reloaded = DetectorConfig.from_dict(d)
        assert reloaded == det

    def test_from_dict_defaults(self) -> None:
        det = DetectorConfig.from_dict({"id": "det1"})
        assert det.name == ""
        assert det.room == ""
        assert det.active is True


class TestNestedPushbuttons:
    def test_parse_reads_nested_pushbuttons(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {
                    "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {"id": "2f8185190000df", "channel": 1, "name": "Badkamer knop", "room": "1e verdieping"}
                    ],
                }
            ]
        }
        p = tmp_path / "nested.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        cfg = InstallationConfig.load(p)

        assert len(cfg.pushbuttons) == 1
        btn = cfg.pushbutton_by_id("2f8185190000df")
        assert btn is not None
        assert btn.channel == 1
        assert btn.module_id == "00:24:77:52:ad:aa"

    def test_pushbutton_threshold_default_when_unknown(self, tmp_path: Path) -> None:
        p = tmp_path / "empty.json"
        p.write_text(json.dumps({"modules": []}), encoding="utf-8")
        cfg = InstallationConfig.load(p)
        from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S
        assert cfg.pushbutton_threshold("unknown") == DEFAULT_BUTTON_HOLD_THRESHOLD_S

    def test_old_flat_buttons_format_rejected(self, tmp_path: Path) -> None:
        data = {
            "modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"}],
            "buttons": [{"id": "2f8185190000df", "module_id": "00:24:77:52:ad:aa"}],
        }
        p = tmp_path / "old_format.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="migrate_buttons_to_nested"):
            InstallationConfig.load(p)

    def test_duplicate_pushbutton_id_rejected(self, tmp_path: Path) -> None:
        data = {
            "modules": [
                {
                    "name": "IP1100PoE", "ip": "10.10.1.50", "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {"id": "2f8185190000df", "name": "A"},
                        {"id": "2f8185190000df", "name": "B"},
                    ],
                }
            ]
        }
        p = tmp_path / "dup.json"
        p.write_text(json.dumps(data), encoding="utf-8")
        with pytest.raises(InstallationError, match="Duplicate"):
            InstallationConfig.load(p)
