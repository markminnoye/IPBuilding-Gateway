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
    validate_channel_fields,
    validate_pushbutton_fields,
)
from gateway.installation import InstallationConfig


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
