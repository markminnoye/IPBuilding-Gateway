"""Gateway version must track ipbuilding_gateway/config.yaml."""

from __future__ import annotations

import re
from pathlib import Path

from gateway import __version__

_CONFIG = Path(__file__).resolve().parent.parent / "ipbuilding_gateway" / "config.yaml"
_VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def _config_version() -> str:
    match = _VERSION_RE.search(_CONFIG.read_text(encoding="utf-8"))
    assert match, "version: missing from ipbuilding_gateway/config.yaml"
    return match.group(1)


def test_gateway_version_matches_addon_config() -> None:
    assert __version__ == _config_version()
