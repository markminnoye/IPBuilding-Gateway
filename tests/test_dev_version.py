"""Dev-channel version derivation for the develop add-on image."""

from __future__ import annotations

from pathlib import Path

import pytest

from scripts.dev_version import (
    is_dev_version,
    is_older_dev,
    next_dev_version,
    read_version,
    write_version,
)

_REPO_CONFIG = Path(__file__).resolve().parent.parent / "ipbuilding_gateway" / "config.yaml"
_BUILD_APP = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "build-app.yaml"
_DEVELOP_IMAGE = (
    Path(__file__).resolve().parent.parent / ".github" / "workflows" / "develop-image.yaml"
)
_BUILDER = Path(__file__).resolve().parent.parent / ".github" / "workflows" / "builder.yaml"


def _config(path: Path, version: str) -> None:
    path.write_text(
        f'name: Example\nversion: "{version}"\nslug: example\n',
        encoding="utf-8",
    )


def test_release_version_opens_next_minor(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config, "1.7.0")
    assert next_dev_version(read_version(config), 4) == "1.8.0-dev.4"


def test_existing_dev_version_keeps_base_and_uses_run_number() -> None:
    assert next_dev_version("1.8.0-dev.3", 12) == "1.8.0-dev.12"


def test_run_number_must_be_positive() -> None:
    with pytest.raises(ValueError):
        next_dev_version("1.7.0", 0)


def test_unsupported_version_is_rejected() -> None:
    with pytest.raises(ValueError):
        next_dev_version("latest", 1)
    with pytest.raises(ValueError):
        next_dev_version("1.8.0-beta", 1)


def test_write_only_accepts_dev_versions(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config, "1.7.0")
    with pytest.raises(ValueError):
        write_version(config, "1.8.0")
    with pytest.raises(ValueError):
        write_version(config, "latest")
    assert read_version(config) == "1.7.0"


def test_write_replaces_version_and_keeps_quotes(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config, "1.7.0")
    assert write_version(config, "1.8.0-dev.2") is True
    text = config.read_text(encoding="utf-8")
    assert 'version: "1.8.0-dev.2"' in text
    assert read_version(config) == "1.8.0-dev.2"
    assert write_version(config, "1.8.0-dev.2") is False


def test_no_downgrade_keeps_the_higher_dev_number(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config, "1.8.0-dev.9")
    assert write_version(config, "1.8.0-dev.4", no_downgrade=True) is False
    assert read_version(config) == "1.8.0-dev.9"
    assert write_version(config, "1.8.0-dev.10", no_downgrade=True) is True
    assert read_version(config) == "1.8.0-dev.10"


def test_no_downgrade_keeps_a_newer_base(tmp_path: Path) -> None:
    config = tmp_path / "config.yaml"
    _config(config, "1.9.0-dev.1")
    assert write_version(config, "1.8.0-dev.40", no_downgrade=True) is False
    assert read_version(config) == "1.9.0-dev.1"


def test_repo_config_version_is_a_shape_the_workflow_understands() -> None:
    version = read_version(_REPO_CONFIG)
    assert is_dev_version(version) or version.count(".") == 2
    next_dev_version(version, 1)


def test_older_dev_helper() -> None:
    assert is_older_dev("1.8.0-dev.5", "1.8.0-dev.5") is True
    assert is_older_dev("1.8.0-dev.5", "1.8.0-dev.6") is False
    assert is_older_dev("1.7.0", "1.8.0-dev.1") is False


def test_workflows_publish_dev_tags_only_from_develop() -> None:
    develop = _DEVELOP_IMAGE.read_text(encoding="utf-8")
    assert "branches:" in develop
    assert "- develop" in develop
    assert "tags:" not in develop
    assert "version_override:" in develop
    assert "[skip ci]" in develop
    assert "scripts/addon_channel.py develop" in develop

    build_app = _BUILD_APP.read_text(encoding="utf-8")
    assert "version_override:" in build_app
    assert "default: \"\"" in build_app
    assert "inputs.version_override == '' && github.ref_name == 'main'" in build_app
    assert "github.ref_name == 'develop'" in build_app
    assert "scripts/dev_version.py check" in build_app
    assert "scripts/addon_channel.py develop" in build_app
    assert "scripts/addon_channel.py stable" not in build_app

    builder = _BUILDER.read_text(encoding="utf-8")
    assert 'tags:\n      - "v*.*.*"' in builder
    assert "develop" not in builder.split("on:", 1)[1].split("jobs:", 1)[0]
