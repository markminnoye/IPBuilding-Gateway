"""Tests for legacy central HTML import parser."""

from __future__ import annotations

from pathlib import Path

from scripts.legacy_central_parser import parse_legacy_central_html

FIXTURE = Path(__file__).resolve().parent / "fixtures" / "legacy_central" / "search_items.html"


def test_legacy_html_fixture_parses_modules() -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    doc = parse_legacy_central_html(html)
    assert len(doc["modules"]) == 2

    relay = next(m for m in doc["modules"] if m["ip"] == "10.10.1.32")
    assert relay["type"] == "relay"
    assert len(relay["channels"]) == 2
    ch0 = next(c for c in relay["channels"] if c["ch"] == 0)
    assert ch0["name"] == "Verlichting garage"
    assert ch0["room"] == "Verlichting"
    assert ch0["active"] is False

    dimmer = next(m for m in doc["modules"] if m["ip"] == "10.10.1.40")
    assert dimmer["type"] == "dimmer"
    ch2 = dimmer["channels"][0]
    assert ch2["name"] == "Woonkamer spots"
    assert ch2["room"] == "Woonkamer"
