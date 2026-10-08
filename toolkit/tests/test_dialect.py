"""Dialect city names. Previous ids stay inside the alias module."""

from __future__ import annotations

from pathlib import Path

from ipbuilding_debug.dialect import (
    DIALECTS,
    KESSEL_LO,
    TORHOUT,
    dialect_name,
    legacy_segments,
    present_dialect_id,
)
from ipbuilding_debug.tools import decode_test

TOOLKIT = Path(__file__).resolve().parents[1]


def test_ids_and_names_come_from_one_catalogue() -> None:
    assert [item.name for item in DIALECTS] == ["Kessel-Lo", "Torhout"]
    assert KESSEL_LO.id == "kessel-lo"
    assert TORHOUT.id == "torhout"
    assert KESSEL_LO.message_types == ["dimmer.kessel-lo.*", "input.kessel-lo.*"]
    assert TORHOUT.message_types == ["*.torhout.*"]
    assert KESSEL_LO.id in KESSEL_LO.description
    assert TORHOUT.name in TORHOUT.description


def test_legacy_segments_display_as_the_current_city() -> None:
    from ipbuilding_debug import dialect as dialect_mod

    assert len(legacy_segments()) == len(DIALECTS)
    for segment, dialect in dialect_mod._LEGACY.items():
        families = dialect.families or ("relay", "dimmer", "input")
        for family in families:
            incoming = f"{family}.{segment}.status_reply"
            shown = present_dialect_id(incoming)
            assert shown == f"{family}.{dialect.id}.status_reply"
            assert segment not in shown
            assert dialect_name(incoming) == dialect.name


def test_decode_test_names_the_city_and_hides_the_previous_id() -> None:
    first = decode_test("I0154110")
    second = decode_test("I0115100")
    assert "Kessel-Lo" in first.message
    assert first.data["dialects"][0]["id"] == "kessel-lo"
    assert "dimmer.kessel-lo.status_reply" in first.render()
    assert "Torhout" in second.message
    assert second.data["dialects"][0]["id"] == "torhout"
    assert "dimmer.torhout.status_reply" in second.render()
    blob = first.render() + second.render()
    for segment in legacy_segments():
        assert f".{segment}." not in blob


def test_previous_ids_are_not_written_outside_the_alias() -> None:
    """Longer previous ids must not leak into docs, tests, or other modules."""
    watched = [segment for segment in legacy_segments() if len(segment) >= 4]
    assert watched
    skip = {".build", "dist", "__pycache__", ".pytest_cache"}
    offenders: list[str] = []
    for path in TOOLKIT.rglob("*"):
        if not path.is_file() or path.suffix == ".pyc":
            continue
        if skip.intersection(path.relative_to(TOOLKIT).parts):
            continue
        if path.name == "dialect.py":
            continue
        text = path.read_text(encoding="utf-8", errors="replace")
        for segment in watched:
            if segment in text:
                offenders.append(f"{path.relative_to(TOOLKIT)}: {segment}")
    assert offenders == []
