"""Tests for scripts/migrate_button_ids.py."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from scripts.migrate_button_ids import migrate, migrate_file


def test_migrate_converts_ten_and_fourteen_hex() -> None:
    raw = {
        "modules": [
            {
                "name": "IP1100PoE",
                "ip": "10.10.1.50",
                "type": "input",
                "pushbuttons": [
                    {"id": "2f8185190000df", "name": "Badkamer", "room": "1e", "active": True},
                    {"id": "dac46cc330", "name": "Keuken", "room": "Gelijkvloers", "active": False},
                    {"id": "e341851f", "name": "Already canonical", "room": "", "active": True},
                ],
            },
            {
                "name": "IP0200PoE",
                "ip": "10.10.1.30",
                "type": "relay",
                "channels": [{"ch": 0, "name": "Keuken", "active": True}],
            },
        ]
    }
    result = migrate(raw)

    input_mod = next(m for m in result["modules"] if m["type"] == "input")
    ids = [b["id"] for b in input_mod["pushbuttons"]]
    assert ids == ["2f8185df", "dac46cc3", "e341851f"]
    assert input_mod["pushbuttons"][0]["name"] == "Badkamer"
    assert input_mod["pushbuttons"][1]["room"] == "Gelijkvloers"
    assert input_mod["pushbuttons"][1]["active"] is False
    relay = next(m for m in result["modules"] if m["type"] == "relay")
    assert relay["channels"][0]["name"] == "Keuken"


def test_migrate_warns_on_canonical_collision(caplog) -> None:
    raw = {
        "modules": [{
            "name": "IP1100PoE",
            "ip": "10.10.1.50",
            "type": "input",
            "pushbuttons": [
                {"id": "dac46cc330", "name": "First"},
                {"id": "dac46c100000c3", "name": "Second"},
            ],
        }]
    }
    result = migrate(raw)
    buttons = result["modules"][0]["pushbuttons"]
    assert len(buttons) == 1
    assert buttons[0]["id"] == "dac46cc3"
    assert buttons[0]["name"] == "First"
    assert "collision" in caplog.text.lower()


def test_migrate_is_idempotent() -> None:
    raw = {
        "modules": [{
            "type": "input",
            "ip": "10.10.1.50",
            "pushbuttons": [{"id": "2f8185df", "name": "X"}],
        }]
    }
    once = migrate(raw)
    twice = migrate(once)
    assert twice == once
    assert twice["modules"][0]["pushbuttons"][0]["id"] == "2f8185df"


def test_migrate_file_writes_backup_and_result(tmp_path: Path) -> None:
    devices_file = tmp_path / "devices.json"
    original = {
        "modules": [{
            "type": "input",
            "ip": "10.10.1.50",
            "pushbuttons": [{"id": "dac46cc330", "name": "Keuken"}],
        }]
    }
    devices_file.write_text(json.dumps(original), encoding="utf-8")

    migrate_file(devices_file)

    backup = tmp_path / "devices.json.bak"
    assert backup.exists()
    assert json.loads(backup.read_text(encoding="utf-8")) == original

    migrated = json.loads(devices_file.read_text(encoding="utf-8"))
    assert migrated["modules"][0]["pushbuttons"][0]["id"] == "dac46cc3"
    assert migrated["modules"][0]["pushbuttons"][0]["name"] == "Keuken"


def test_migrate_file_missing_path_raises(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        migrate_file(tmp_path / "nonexistent.json")
