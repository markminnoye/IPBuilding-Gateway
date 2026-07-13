"""Tests for scripts/migrate_buttons_to_nested.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.migrate_buttons_to_nested import migrate, migrate_file


def test_migrate_moves_flat_buttons_into_matching_module() -> None:
    raw = {
        "modules": [
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "00:24:77:52:ad:aa"},
            {"name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []},
        ],
        "buttons": [
            {"id": "2f8185190000df", "module_id": "00:24:77:52:ad:aa", "name": "Badkamer knop",
             "room": "1e verdieping", "active": True, "hold_threshold_s": 1.5},
        ],
    }
    result = migrate(raw)

    assert "buttons" not in result
    input_module = next(m for m in result["modules"] if m["mac"] == "00:24:77:52:ad:aa")
    assert len(input_module["pushbuttons"]) == 1
    assert input_module["pushbuttons"][0]["id"] == "2f8185190000df"
    assert "module_id" not in input_module["pushbuttons"][0]
    assert input_module["detectors"] == []


def test_migrate_adds_empty_detectors_to_input_modules_without_it() -> None:
    raw = {"modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1"}], "buttons": []}
    result = migrate(raw)
    input_module = result["modules"][0]
    assert input_module["detectors"] == []
    assert input_module["pushbuttons"] == []


def test_migrate_warns_and_skips_orphan_button(caplog) -> None:
    raw = {
        "modules": [{"name": "IP0200PoE", "ip": "10.10.1.30", "type": "relay", "mac": "00:24:77:52:ac:be", "channels": []}],
        "buttons": [{"id": "orphan1", "module_id": "nonexistent_mac", "name": "Orphan"}],
    }
    result = migrate(raw)
    assert "buttons" not in result
    relay_module = result["modules"][0]
    assert "pushbuttons" not in relay_module  # relay modules don't get a pushbuttons key
    assert "no matching module" in caplog.text.lower() or "orphan" in caplog.text.lower()


def test_migrate_is_idempotent_when_already_nested() -> None:
    raw = {
        "modules": [
            {"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1",
             "pushbuttons": [{"id": "abc", "name": "X"}], "detectors": []},
        ]
    }
    result = migrate(raw)
    assert result == raw


def test_migrate_file_writes_backup_and_result(tmp_path: Path) -> None:
    devices_file = tmp_path / "devices.json"
    original = {
        "modules": [{"name": "IP1100PoE", "ip": "10.10.1.50", "type": "input", "mac": "mac1"}],
        "buttons": [{"id": "abc", "module_id": "mac1", "name": "Knop"}],
    }
    devices_file.write_text(json.dumps(original), encoding="utf-8")

    migrate_file(devices_file)

    backup = tmp_path / "devices.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == original

    migrated = json.loads(devices_file.read_text(encoding="utf-8"))
    assert "buttons" not in migrated
    assert migrated["modules"][0]["pushbuttons"][0]["id"] == "abc"


def test_migrate_file_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrate_file(tmp_path / "nonexistent.json")
