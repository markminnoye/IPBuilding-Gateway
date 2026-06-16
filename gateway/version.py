"""Resolve the gateway release version.

Single source of truth: ``ipbuilding_gateway/config.yaml`` ``version:`` field
(required by the HA add-on manifest and CI image tags).

The runtime version exposed via ``/api/v1/status`` and HA discovery is read
from that same file at import time — in local dev, in pytest, and in the
Docker image. ``prepare-build.sh`` stages ``config.yaml`` into the add-on
context so the relative path resolves inside the image as well.

There is no generated ``gateway/_version.py`` and no build-time stamping.
Bumping the version in ``config.yaml`` is the only step that changes the
reported version everywhere.

Resolution order:
1. ``GATEWAY_VERSION`` environment variable (optional override, mainly tests/CI)
2. ``ipbuilding_gateway/config.yaml`` in the working tree (= in the image)
3. ``0.0.0-dev`` fallback when the file is missing
"""

from __future__ import annotations

import os
import re
from pathlib import Path

_CONFIG_REL = Path("ipbuilding_gateway") / "config.yaml"
_VERSION_RE = re.compile(r'^version:\s*"?([^"\n]+)"?\s*$', re.MULTILINE)


def _repo_root() -> Path:
    return Path(__file__).resolve().parent.parent


def _config_yaml_path() -> Path | None:
    candidate = _repo_root() / _CONFIG_REL
    return candidate if candidate.is_file() else None


def _parse_config_version(path: Path) -> str | None:
    match = _VERSION_RE.search(path.read_text(encoding="utf-8"))
    return match.group(1) if match else None


def resolve_version() -> str:
    override = os.environ.get("GATEWAY_VERSION", "").strip()
    if override:
        return override

    config_path = _config_yaml_path()
    if config_path is not None:
        parsed = _parse_config_version(config_path)
        if parsed:
            return parsed

    return "0.0.0-dev"


__version__ = resolve_version()
