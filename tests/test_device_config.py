"""Tests for gateway.device_config — PATCH validation and mutation."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from gateway.device_config import (
    DeviceConfigError,
    apply_channel_patch,
    apply_pushbutton_patch,
    installation_to_raw_dict,
    sync_input_pushbuttons_from_cache,
    validate_channel_fields,
    validate_devices_document,
    validate_pushbutton_fields,
)
from gateway.installation import InstallationConfig
from gateway.module_metadata import ModuleMetadata, ModuleMetadataCache


def _sample_installation() -> InstallationConfig:
    return InstallationConfig._parse({
        "modules": [
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
                    {
                        "id": "2f8185190000df",
                        "name": "Badkamer",
                        "room": "1e verdieping",
                        "active": True,
                        "hold_threshold_s": 1.5,
                    }
                ],
            },
        ],
    })


class TestValidateChannelFields:
    def test_valid_fields(self) -> None:
        result = validate_channel_fields(
            {"name": "Lamp", "room": "Hal", "semantic_type": "switch", "active": False, "max_watt": 0}
        )
        assert result == {
            "name": "Lamp",
            "room": "Hal",
            "semantic_type": "switch",
            "active": False,
            "max_watt": 0,
        }

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"ip": "10.10.1.30"})
        assert exc.value.code == "unknown_field"
        assert "ip" in exc.value.details["fields"]

    def test_invalid_semantic_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"semantic_type": "sensor"})
        assert exc.value.code == "validation"

    def test_bad_active_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"active": "yes"})
        assert exc.value.code == "validation"

    def test_bad_max_watt_type(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_channel_fields({"max_watt": -1})
        assert exc.value.code == "validation"


class TestValidatePushbuttonFields:
    def test_valid_fields(self) -> None:
        result = validate_pushbutton_fields({"name": "Knop", "room": "Bad", "active": True})
        assert result == {"name": "Knop", "room": "Bad", "active": True}

    def test_unknown_field_raises(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_pushbutton_fields({"hold_threshold_s": 2.0})
        assert exc.value.code == "unknown_field"

    def test_channel_not_patchable(self) -> None:
        with pytest.raises(DeviceConfigError) as exc:
            validate_pushbutton_fields({"channel": 2})
        assert exc.value.code == "unknown_field"


class TestApplyPatches:
    def test_apply_channel_patch(self) -> None:
        inst = _sample_installation()
        apply_channel_patch(inst, "10.10.1.30", 0, {"room": "Eetkamer", "max_watt": 40})
        ch = inst.module_by_ip("10.10.1.30").channels[0]
        assert ch.room == "Eetkamer"
        assert ch.max_watt == 40
        assert ch.name == "Keuken LED"

    def test_apply_pushbutton_patch(self) -> None:
        inst = _sample_installation()
        apply_pushbutton_patch(inst, "2f8185190000df", {"name": "Douche", "active": False})
        btn = inst.pushbutton_by_id("2f8185190000df")
        assert btn is not None
        assert btn.name == "Douche"
        assert btn.active is False


class TestInstallationToRawDict:
    def test_pushbuttons_preserved_on_channel_patch_round_trip(self, tmp_path: Path) -> None:
        """Regression: channel PATCH serialization must keep the other module's pushbuttons."""
        inst = _sample_installation()
        apply_channel_patch(inst, "10.10.1.30", 0, {"room": "Nieuwe kamer"})

        raw = installation_to_raw_dict(inst)
        assert "buttons" not in raw
        input_module = next(m for m in raw["modules"] if m["type"] == "input")
        assert len(input_module["pushbuttons"]) == 1
        assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
        relay_module = next(m for m in raw["modules"] if m["type"] == "relay")
        assert relay_module["channels"][0]["room"] == "Nieuwe kamer"

        devices_file = tmp_path / "devices.json"
        devices_file.write_text(json.dumps(raw), encoding="utf-8")
        reloaded = InstallationConfig.load(devices_file)
        assert len(reloaded.pushbuttons) == 1
        assert reloaded.module_by_ip("10.10.1.30").channels[0].room == "Nieuwe kamer"

    def test_no_top_level_buttons_key(self) -> None:
        inst = InstallationConfig._parse({"modules": []})
        raw = installation_to_raw_dict(inst)
        assert raw == {"modules": []}


class TestSyncInputPushbuttonsFromCache:
    def test_merge_preserves_operator_fields_and_seeds_new_button(self) -> None:
        inst = _sample_installation()
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            network={},
            buttons=[
                {
                    "index": 1,
                    "id": "2D2F8185190000DF",
                    "descr": "Wire Badkamer",
                    "gr": "Wire verdieping",
                    "func2": {"holdSeconds": 2.0},
                },
                {
                    "index": 2,
                    "id": "2DE341851900001F",
                    "descr": "Nieuwe knop",
                    "gr": "Hal",
                },
            ],
        )

        count = sync_input_pushbuttons_from_cache(inst, cache)
        assert count == 1

        existing = inst.pushbutton_by_id("2f8185190000df")
        assert existing is not None
        assert existing.name == "Badkamer"
        assert existing.room == "1e verdieping"
        assert existing.active is True
        assert existing.hold_threshold_s == 1.5
        assert existing.channel == 1

        new_btn = inst.pushbutton_by_id("e341851900001f")
        assert new_btn is not None
        assert new_btn.name == "Nieuwe knop"
        assert new_btn.room == "Hal"
        assert new_btn.channel == 2

    def test_merge_fills_missing_name_room_and_channel_from_wire(self) -> None:
        inst = InstallationConfig._parse({
            "modules": [
                {
                    "name": "IP1100PoE",
                    "ip": "10.10.1.50",
                    "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {
                            "id": "2f8185190000df",
                            "name": "",
                            "room": "",
                            "active": True,
                            "hold_threshold_s": 1.5,
                        }
                    ],
                }
            ],
        })
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            network={},
            buttons=[
                {
                    "index": 3,
                    "id": "2D2F8185190000DF",
                    "descr": "From wire",
                    "gr": "From room",
                }
            ],
        )

        sync_input_pushbuttons_from_cache(inst, cache)
        btn = inst.pushbutton_by_id("2f8185190000df")
        assert btn is not None
        assert btn.name == "From wire"
        assert btn.room == "From room"
        assert btn.channel == 3

    def test_merge_canonicalizes_legacy_button_id_casing_and_prefix(self) -> None:
        inst = InstallationConfig._parse({
            "modules": [
                {
                    "name": "IP1100PoE",
                    "ip": "10.10.1.50",
                    "type": "input",
                    "mac": "00:24:77:52:ad:aa",
                    "pushbuttons": [
                        {
                            "id": "2D2F8185190000DF",
                            "name": "Badkamer",
                            "room": "1e verdieping",
                            "active": True,
                            "hold_threshold_s": 1.5,
                        }
                    ],
                }
            ],
        })
        cache = ModuleMetadataCache()
        cache._by_mac["00:24:77:52:ad:aa"] = ModuleMetadata(
            network={},
            buttons=[
                {
                    "index": 1,
                    "id": "2D2F8185190000DF",
                    "descr": "Wire Badkamer",
                    "gr": "Wire verdieping",
                }
            ],
        )

        sync_input_pushbuttons_from_cache(inst, cache)

        input_module = next(m for m in inst.modules if m.type.value == "input")
        assert len(input_module.pushbuttons) == 1
        assert input_module.pushbuttons[0].id == "2f8185190000df"
        assert input_module.pushbuttons[0].name == "Badkamer"

        reloaded = InstallationConfig._parse(installation_to_raw_dict(inst))
        assert reloaded.pushbutton_by_id("2f8185190000df") is not None


class TestValidateDevicesDocument:
    def test_accepts_empty_modules(self) -> None:
        raw = {"modules": []}
        assert validate_devices_document(raw) == raw

    def test_accepts_well_formed_document(self) -> None:
        raw = {
            "modules": [
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
            ]
        }
        assert validate_devices_document(raw) == raw

    def test_rejects_non_dict(self) -> None:
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document([1, 2, 3])
        assert exc_info.value.code == "invalid_devices_file"

    def test_rejects_duplicate_mac(self) -> None:
        raw = {
            "modules": [
                {"name": "A", "ip": "10.10.1.30", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
                {"name": "B", "ip": "10.10.1.31", "type": "relay",
                 "mac": "00:24:77:52:ac:be", "channels": []},
            ]
        }
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"
        assert "Duplicate module MAC" in exc_info.value.message

    def test_rejects_unknown_module_type(self) -> None:
        raw = {"modules": [{"name": "A", "ip": "10.10.1.30", "type": "bogus"}]}
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"

    def test_rejects_old_flat_buttons_format(self) -> None:
        raw = {"modules": [], "buttons": []}
        with pytest.raises(DeviceConfigError) as exc_info:
            validate_devices_document(raw)
        assert exc_info.value.code == "invalid_devices_file"
        assert "Old flat devices.json format" in exc_info.value.message
