"""Tests for gateway.ipa_parser — IP1100PoE .IPA autonomy EEPROM dumps."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.installation import InstallationConfig
from gateway.ipa_parser import (
    build_devices_json_from_ipa,
    input_ip_from_ipa_filename,
    merge_devices_json,
    module_type_from_ip,
    parse_ipa_file,
)

# Minimal valid record: one button → relay .30 ch 2/3
_SAMPLE_IPA = """\
88
19
6C
31
42
31
FF
T
47
50
7C
A8
30
32
33
T
FF
FF
FF
"""


_REFERENCE_IPA = (
    Path(__file__).resolve().parents[1]
    / "resources_and_docs/reference/samples/10.10.1.55.IPA"
)


@pytest.fixture
def reference_ipa_path() -> Path:
    if not _REFERENCE_IPA.exists():
        pytest.skip(f"reference IPA sample missing: {_REFERENCE_IPA}")
    return _REFERENCE_IPA


class TestIpaFilename:
    def test_input_ip_from_dotted_filename(self) -> None:
        assert input_ip_from_ipa_filename("10.10.1.55.IPA") == "10.10.1.55"
        assert input_ip_from_ipa_filename("/tmp/foo/10.10.1.50.IPA") == "10.10.1.50"
        assert input_ip_from_ipa_filename("backup.IPA") is None


class TestModuleTypeHeuristic:
    def test_installer_ranges(self) -> None:
        assert module_type_from_ip("10.10.1.30") == "relay"
        assert module_type_from_ip("10.10.1.32") == "relay"
        assert module_type_from_ip("10.10.1.40") == "dimmer"
        assert module_type_from_ip("10.10.1.42") == "dimmer"
        assert module_type_from_ip("10.10.1.55") == "input"
        assert module_type_from_ip("10.10.1.1") == "unknown"


class TestParseIpaFile:
    def test_parse_minimal_sample(self, tmp_path: Path) -> None:
        ipa = tmp_path / "10.10.1.55.IPA"
        ipa.write_text(_SAMPLE_IPA, encoding="utf-8")
        result = parse_ipa_file(ipa)
        assert result.input_ip == "10.10.1.55"
        assert len(result.buttons) == 1
        btn = result.buttons[0]
        assert btn.button_id == "88196c3142"
        assert btn.input_port == 1
        assert len(btn.targets) == 2
        assert btn.targets[0].ip == "10.10.1.30"
        assert btn.targets[0].channel == 2
        assert btn.targets[1].channel == 3

    def test_reference_ipa_has_sixteen_buttons(self, reference_ipa_path: Path) -> None:
        result = parse_ipa_file(reference_ipa_path)
        assert result.input_ip == "10.10.1.55"
        assert len(result.buttons) == 16
        ports = {b.input_port for b in result.buttons}
        assert ports == {0, 1, 2}

    def test_reference_ipa_target_modules(self, reference_ipa_path: Path) -> None:
        draft = build_devices_json_from_ipa(parse_ipa_file(reference_ipa_path))
        ips = {m["ip"]: m["type"] for m in draft["modules"]}
        assert ips["10.10.1.55"] == "input"
        assert ips["10.10.1.30"] == "relay"
        assert ips["10.10.1.32"] == "relay"
        assert ips["10.10.1.42"] == "dimmer"

    def test_generated_document_loads(self, reference_ipa_path: Path) -> None:
        draft = build_devices_json_from_ipa(parse_ipa_file(reference_ipa_path))
        InstallationConfig._parse(draft)


class TestBuildDevicesJson:
    def test_full_profile_activates_all_channels(self, tmp_path: Path) -> None:
        ipa = tmp_path / "10.10.1.55.IPA"
        ipa.write_text(_SAMPLE_IPA, encoding="utf-8")
        draft = build_devices_json_from_ipa(parse_ipa_file(ipa), profile="full")
        relay = next(m for m in draft["modules"] if m["ip"] == "10.10.1.30")
        assert all(c["active"] for c in relay["channels"])
        input_mod = next(m for m in draft["modules"] if m["type"] == "input")
        assert input_mod["pushbuttons"][0]["channel"] == 1

    def test_conservative_profile_limits_relay_channels(self, tmp_path: Path) -> None:
        ipa = tmp_path / "10.10.1.55.IPA"
        ipa.write_text(_SAMPLE_IPA, encoding="utf-8")
        draft = build_devices_json_from_ipa(
            parse_ipa_file(ipa), profile="conservative",
        )
        relay = next(m for m in draft["modules"] if m["ip"] == "10.10.1.30")
        active = [c for c in relay["channels"] if c["active"]]
        assert len(active) == 1
        assert active[0]["ch"] == 2


class TestMergeDevicesJson:
    def test_merge_does_not_clobber_existing_names(self) -> None:
        base = {
            "modules": [{
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "model": "IP0200PoE",
                "mac": "00:24:77:52:ac:be",
                "firmware": "5.1",
                "channels": [{
                    "ch": 0,
                    "name": "Keuken",
                    "room": "Keuken",
                    "semantic_type": "light",
                    "active": True,
                    "max_watt": 60,
                }],
            }],
        }
        incoming = {
            "modules": [{
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "model": "IP0200PoE",
                "mac": "",
                "firmware": "",
                "channels": [
                    {"ch": 0, "name": "Kanaal 0", "room": "Onbekend",
                     "semantic_type": "light", "active": True, "max_watt": 60},
                    {"ch": 2, "name": "Kanaal 2", "room": "Onbekend",
                     "semantic_type": "light", "active": True, "max_watt": 60},
                ],
            }],
        }
        merged = merge_devices_json(base, incoming)
        relay = next(m for m in merged["modules"] if m["ip"] == "10.10.1.30")
        ch0 = next(c for c in relay["channels"] if c["ch"] == 0)
        assert ch0["name"] == "Keuken"
        assert {c["ch"] for c in relay["channels"]} == {0, 2}

    def test_merge_round_trips_through_installation(self, tmp_path: Path) -> None:
        ipa = tmp_path / "10.10.1.55.IPA"
        ipa.write_text(_SAMPLE_IPA, encoding="utf-8")
        incoming = build_devices_json_from_ipa(parse_ipa_file(ipa))
        merged = merge_devices_json({"modules": []}, incoming)
        InstallationConfig._parse(merged)
        json.dumps(merged)
