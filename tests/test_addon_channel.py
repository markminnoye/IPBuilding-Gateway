"""Develop and stable add-on names stay on their own channels."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.addon_channel import (
    DESCRIPTION,
    DEVELOP_NAME,
    STABLE_NAME,
    apply_channel,
)

_REPO = Path(__file__).resolve().parent.parent
_CONFIG = _REPO / "ipbuilding_gateway" / "config.yaml"
_STABLE_WORKFLOW = _REPO / ".github" / "workflows" / "stable-addon-name.yaml"


def _config(path: Path) -> None:
    path.write_text(
        "\n".join(
            [
                f"name: {STABLE_NAME}",
                'version: "1.8.0-dev.3"',
                "slug: ipbuilding_gateway",
                f"description: {DESCRIPTION}",
                f"panel_title: {STABLE_NAME}",
                "",
            ]
        ),
        encoding="utf-8",
    )


def test_develop_channel_renames_store_entry_and_panel(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config)
    assert apply_channel(config, "develop") is True
    text = config.read_text(encoding="utf-8")
    assert f"name: {DEVELOP_NAME}\n" in text
    assert f"panel_title: {DEVELOP_NAME}\n" in text
    assert 'version: "1.8.0-dev.3"' in text
    assert f"description: {DESCRIPTION}" in text
    assert apply_channel(config, "develop") is False


def test_stable_channel_puts_the_release_name_back(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config)
    apply_channel(config, "develop")
    assert apply_channel(config, "stable") is True
    text = config.read_text(encoding="utf-8")
    assert f"name: {STABLE_NAME}\n" in text
    assert f"panel_title: {DEVELOP_NAME}" not in text
    assert f"panel_title: {STABLE_NAME}\n" in text
    assert apply_channel(config, "stable") is False


def test_missing_fields_are_refused(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    config.write_text('version: "1.8.0-dev.3"\n', encoding="utf-8")
    with pytest.raises(ValueError, match="name"):
        apply_channel(config, "develop")
    config.write_text(f"name: {STABLE_NAME}\n", encoding="utf-8")
    with pytest.raises(ValueError, match="panel_title"):
        apply_channel(config, "stable")


def test_committed_manifest_keeps_the_stable_name_and_shared_description() -> None:
    text = _CONFIG.read_text(encoding="utf-8")
    assert f"name: {STABLE_NAME}\n" in text
    assert f"panel_title: {STABLE_NAME}\n" in text
    assert f"description: {DESCRIPTION}\n" in text
    assert "(develop)" not in text
    assert "UDP/1001" not in text.split("description:", 1)[1].split("\n", 1)[0]


def test_about_pages_use_the_shared_description() -> None:
    addon = _REPO / "ipbuilding_gateway"
    for name in ("README.md", "DOCS.md"):
        text = (addon / name).read_text(encoding="utf-8")
        assert DESCRIPTION in text.split("## ", 1)[0]


def test_main_push_restores_the_stable_name() -> None:
    workflow = _STABLE_WORKFLOW.read_text(encoding="utf-8")
    trigger = workflow.split("jobs:", 1)[0]
    assert "branches:" in trigger
    assert "- main" in trigger
    assert "develop" not in trigger.split("on:", 1)[1]
    assert "scripts/addon_channel.py stable" in workflow
    assert "[skip ci]" in workflow
    assert "ipbuilding_gateway/config.yaml" in workflow
