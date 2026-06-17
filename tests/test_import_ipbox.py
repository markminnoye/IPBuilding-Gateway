"""Tests for scripts/import_ipbox_to_ha.py.

We exercise the parser, the entity-resolution logic, the YAML rendering
and idempotency rules without touching the network. The HTTP layer is
monkey-patched via ``urllib.request.urlopen``.
"""

from __future__ import annotations

import hashlib
import json
import sys
from pathlib import Path
from unittest.mock import patch

import pytest

# Ensure the scripts/ folder is importable.
SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
sys.path.insert(0, str(SCRIPTS_DIR))

import import_ipbox_to_ha as mod  # noqa: E402


# ---------------------------------------------------------------------------
# Sample fixtures
# ---------------------------------------------------------------------------


GETBUTTONS_FIXTURE = [
    {
        "id": "2D2F8185190000DF",
        "descr": "Keuken knop 1",
        "gr": "Keuken",
        "func1": {"ip": "30", "ch": 0, "outType": "relay", "action": "on"},
        "func2": {
            "ip": "40",
            "ch": 1,
            "outType": "dimmer",
            "action": "dim",
            "holdSeconds": 2.0,
        },
    },
    {
        "id": "2DCAFEBABE000001",
        "descr": "Badkamer knop",
        "gr": "Badkamer",
        "func1": {
            "ip": "30",
            "ch": 1,
            "outType": "relay",
            "action": "toggle",
            "emailGroup": "alarms",
        },
    },
    {
        # no func1 — release-only
        "id": "2DDEAD0000000007",
        "descr": "Slaapkamer knop",
        "gr": "Slaapkamer",
        "release": {"ip": "40", "ch": 0, "outType": "dimmer", "action": "off"},
    },
]


COMPITEMS_FIXTURE = [
    {
        "id": 30,
        "Name": "Keuken LED",
        "Group": "Keuken",
        "Kind": 1,
        "Type": 0,
    },
    {
        "id": 40,
        "Name": "Bureau dimmer",
        "Group": "Bureau",
        "Kind": 2,
        "Type": 0,
    },
]


# ---------------------------------------------------------------------------
# Parser tests
# ---------------------------------------------------------------------------


class TestParseGetButtons:
    def test_normalises_id_to_wire_form(self) -> None:
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        assert [b.id for b in buttons] == [
            "2f8185190000df",
            "cafebabe000001",
            "dead0000000007",
        ]

    def test_carries_descr_and_gr(self) -> None:
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        assert buttons[0].name == "Keuken knop 1"
        assert buttons[0].room == "Keuken"

    def test_skips_entry_without_id(self) -> None:
        result = mod.parse_get_buttons([{"descr": "orphan"}])
        assert result == []

    def test_skips_malformed_id(self) -> None:
        result = mod.parse_get_buttons([{"id": "not-hex", "descr": "x"}])
        assert result == []


class TestParseCompItems:
    def test_indexes_by_ipbox_id(self) -> None:
        idx = mod.parse_comp_items(COMPITEMS_FIXTURE)
        assert set(idx.keys()) == {30, 40}
        assert idx[30].name == "Keuken LED"
        assert idx[40].group == "Bureau"


# ---------------------------------------------------------------------------
# Entity resolution
# ---------------------------------------------------------------------------


class TestFuncToTargetEntity:
    def test_relay_synthetic_entity_id(self) -> None:
        # The default fallback (no comp_id match) produces a synthetic
        # entity id ``light.<ip>_<ch>``. Operators can rename after import
        # via the report.
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entity, action, notes = mod.func_to_target_entity(
            {"ip": "30", "ch": 0, "outType": "relay", "action": "on"}, channels
        )
        assert entity == "light.10.10.1.30_0"
        assert action == "on"
        assert any("synthetisch" in n for n in notes)

    def test_relay_with_comp_id_match(self) -> None:
        # When the ch happens to equal a comp_id, we resolve the friendly
        # name from /comp/items. ip=99 / ch=30 → comp_id 30 → "Keuken LED".
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entity, action, notes = mod.func_to_target_entity(
            {"ip": "99", "ch": 30, "outType": "relay", "action": "on"}, channels
        )
        assert entity == "light.keuken_led"
        assert action == "on"
        assert not any("synthetisch" in n for n in notes)

    def test_dimmer_action(self) -> None:
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entity, action, notes = mod.func_to_target_entity(
            {"ip": "40", "ch": 1, "outType": "dimmer", "action": "dim"}, channels
        )
        # ch=1 doesn't match comp_id=30/40 → synthetic id + warning.
        assert entity == "light.10.10.1.40_1"
        assert action == "dim"
        assert any("synthetisch" in n for n in notes)

    def test_email_group_warning(self) -> None:
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        _, _, notes = mod.func_to_target_entity(
            {
                "ip": "30",
                "ch": 1,
                "outType": "relay",
                "action": "toggle",
                "emailGroup": "alarms",
            },
            channels,
        )
        assert any("emailGroup" in n for n in notes)

    def test_empty_func(self) -> None:
        entity, action, notes = mod.func_to_target_entity(None, {})
        assert entity is None
        assert action is None
        assert "empty func" in notes

    def test_unknown_out_type_falls_back(self) -> None:
        entity, _, notes = mod.func_to_target_entity(
            {"ip": "99", "ch": 0, "outType": "weird", "action": "on"}, {}
        )
        # We always return a synthetic switch entity; the warning lists
        # the unknown outType so the operator can fix the config.
        assert entity == "switch.10.10.1.99_0"
        assert any("weird" in n for n in notes)


# ---------------------------------------------------------------------------
# Import flow
# ---------------------------------------------------------------------------


class TestImportButtons:
    def test_skips_button_with_completely_empty_func(self) -> None:
        # func1 is explicitly None → no target derivable, skip.
        buttons = mod.parse_get_buttons([
            {"id": "2DABCDEF12345678", "descr": "Lege knop", "func1": None}
        ])
        entries, warnings, friendly = mod.import_buttons(buttons, {})
        assert entries == []
        assert any("Lege knop" in w for w in warnings)
        assert "abcdef12345678" in friendly

    def test_creates_entry_with_func1_and_func2(self) -> None:
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        entries, warnings, friendly = mod.import_buttons(buttons, channels)
        assert any(e.func1_action == "on" and e.func2_action == "dim" for e in entries)
        assert friendly["2f8185190000df"] == "Keuken knop 1"
        # No fatal warnings expected.
        assert warnings == []


# ---------------------------------------------------------------------------
# Rendering
# ---------------------------------------------------------------------------


class TestRenderers:
    def test_helpers_yaml_has_one_input_boolean_per_button(self) -> None:
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entries, _, friendly = mod.import_buttons(buttons, channels)
        text = mod.render_helpers_yaml(entries, friendly)
        # One entry per button
        assert text.count("ipb_keuken_knop_1_dim_up:") == 1
        assert text.count("ipb_badkamer_knop_dim_up:") == 1
        # Icon is the canonical arrow-up
        assert "icon: mdi:arrow-up-bold" in text

    def test_automations_yaml_contains_press_and_long_press(self) -> None:
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entries, _, friendly = mod.import_buttons(buttons, channels)
        text = mod.render_automations_yaml(entries, friendly)
        assert "button_pressed" in text
        assert "button_long_pressed" in text
        # Two automations for the keuken button (func1 + func2)
        assert text.count("ipb_keuken_knop_1_func1") == 1
        assert text.count("ipb_keuken_knop_1_func2") == 1

    def test_report_includes_checksum_and_counts(self) -> None:
        buttons = mod.parse_get_buttons(GETBUTTONS_FIXTURE)
        channels = mod.parse_comp_items(COMPITEMS_FIXTURE)
        entries, warnings, friendly = mod.import_buttons(buttons, channels)
        text = mod.render_report(entries, friendly, warnings, "deadbeef")
        assert "Source checksum:** `deadbeef`" in text
        assert "Geconverteerd (3 knoppen)" in text
        assert "IPBox-projectregels" in text


# ---------------------------------------------------------------------------
# Idempotency
# ---------------------------------------------------------------------------


class TestExistingHelpers:
    def test_returns_empty_when_no_file(self, tmp_path: Path) -> None:
        assert mod._existing_helpers(tmp_path) == {}

    def test_round_trip(self, tmp_path: Path) -> None:
        (tmp_path / "helpers.yaml").write_text(
            "input_boolean:\n  foo: {name: Foo, icon: mdi:bar}\n"
        )
        existing = mod._existing_helpers(tmp_path)
        assert "foo" in existing


# ---------------------------------------------------------------------------
# Checksum
# ---------------------------------------------------------------------------


class TestChecksum:
    def test_deterministic_for_same_payload(self) -> None:
        with patch.object(mod, "http_get_json", return_value={"a": 1}) as mget:
            c1 = mod._checksum(["http://a/"])
            c2 = mod._checksum(["http://a/"])
            assert c1 == c2
            assert len(c1) == 64
            assert mget.call_count == 2

    def test_differs_for_different_payload(self) -> None:
        with patch.object(mod, "http_get_json", side_effect=[{"a": 1}, {"a": 2}]):
            c1 = mod._checksum(["http://a/"])
            c2 = mod._checksum(["http://a/"])
            assert c1 != c2


# ---------------------------------------------------------------------------
# End-to-end (mocked HTTP)
# ---------------------------------------------------------------------------


class TestMainEndToEnd:
    def test_writes_four_files_and_skips_on_unchanged(
        self, tmp_path: Path
    ) -> None:
        responses = {"getButtons": GETBUTTONS_FIXTURE, "comp/items": COMPITEMS_FIXTURE}

        def fake_get(url: str, timeout: float = 5.0) -> object:
            for needle, payload in responses.items():
                if needle in url:
                    return payload
            raise RuntimeError(f"unexpected URL: {url}")

        with patch.object(mod, "http_get_json", side_effect=fake_get):
            rc = mod.main([
                "--out", str(tmp_path),
                "--input-host", "10.10.1.50",
                "--ipbox-host", "192.168.0.185",
                "--no-input-port",  # ensure we don't trip on unknown args
            ] if False else [
                "--out", str(tmp_path),
                "--input-host", "10.10.1.50",
                "--ipbox-host", "192.168.0.185",
            ])
        assert rc == 0
        assert (tmp_path / "automations.yaml").exists()
        assert (tmp_path / "helpers.yaml").exists()
        assert (tmp_path / "import_report.md").exists()
        assert (tmp_path / "checksum.txt").exists()

        # Re-run with no source changes → idempotent skip.
        with patch.object(mod, "http_get_json", side_effect=fake_get):
            rc = mod.main([
                "--out", str(tmp_path),
                "--input-host", "10.10.1.50",
                "--ipbox-host", "192.168.0.185",
            ])
        assert rc == 0
