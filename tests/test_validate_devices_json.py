"""Tests for scripts/validate_devices_json.py."""

import json
from pathlib import Path

import pytest

from scripts.validate_devices_json import validate_devices_file


def test_validate_passes_minimal_config(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text(
        json.dumps({
            "modules": [{
                "ip": "10.10.1.30",
                "type": "relay",
                "mac": "00:24:77:52:ac:be",
                "channels": [
                    {"ch": 0, "name": "A", "room": "B", "active": True},
                ],
            }]
        }),
        encoding="utf-8",
    )
    errors = validate_devices_file(p, expected_active_channels=1)
    assert errors == []


def test_validate_fails_wrong_channel_count(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text('{"modules":[]}', encoding="utf-8")
    errors = validate_devices_file(p, expected_active_channels=28)
    assert any("active channels" in e for e in errors)


def test_validate_fails_duplicate_macs(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text(
        json.dumps({
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []},
                {"ip": "10.10.1.40", "type": "dimmer", "mac": "00:24:77:52:ac:be", "channels": []},
            ]
        }),
        encoding="utf-8",
    )
    errors = validate_devices_file(p)
    assert any("Duplicate module MAC" in e for e in errors)


def test_validate_fails_missing_mac(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text(
        json.dumps({
            "modules": [
                {"ip": "10.10.1.30", "type": "relay", "mac": "", "channels": []},
            ]
        }),
        encoding="utf-8",
    )
    errors = validate_devices_file(p)
    assert any("missing 'mac'" in e for e in errors)


def test_validate_passes_empty_when_no_channel_expectation(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text('{"modules":[]}', encoding="utf-8")
    errors = validate_devices_file(p, expected_active_channels=None)
    assert errors == []


def test_validate_load_error_returns_exc_message(tmp_path: Path):
    p = tmp_path / "devices.json"
    p.write_text("{invalid json", encoding="utf-8")
    errors = validate_devices_file(p)
    assert len(errors) == 1
    assert "expecting" in errors[0].lower() or "json" in errors[0].lower()