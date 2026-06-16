"""Gateway version must track ipbuilding_gateway/config.yaml."""

from __future__ import annotations

import re
from pathlib import Path

from gateway import __version__

_CONFIG = Path(__file__).resolve().parent.parent / "ipbuilding_gateway" / "config.yaml"
_VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)
_AUTO_UPDATE_RE = re.compile(r'^auto_update:\s*(true|false)\s*$', re.MULTILINE)


def _config_version() -> str:
    match = _VERSION_RE.search(_CONFIG.read_text(encoding="utf-8"))
    assert match, "version: missing from ipbuilding_gateway/config.yaml"
    return match.group(1)


def _auto_update() -> str | None:
    match = _AUTO_UPDATE_RE.search(_CONFIG.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def test_gateway_version_matches_addon_config() -> None:
    assert __version__ == _config_version()


def test_auto_update_enabled() -> None:
    """Supervisor must be allowed to pull new add-on images automatically.

    Regression guard: the v0.3.3 image was published but Supervisor kept
    running v0.3.1 because ``auto_update: false`` requires a manual
    upgrade per release. Keep this ``true`` so 0.3.x patches reach HA
    without an operator action.
    """
    assert _auto_update() == "true"
