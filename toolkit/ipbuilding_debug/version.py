"""Toolkit version. Test builds use 0.1.0-rc.N. A release tag gateway-tools-vX.Y.Z must match toolkit/VERSION."""

from __future__ import annotations

import json
from pathlib import Path


def _read_version() -> str:
    """Bundle version from ``VERSION``, then ``manifest.json``.

    In the repo, ``VERSION`` sits next to the package. A packed bundle has
    the same file at its root, and ``manifest.json`` if that file is absent.
    """
    here = Path(__file__).resolve()
    roots = (here.parents[1], here.parent)
    for root in roots:
        path = root / "VERSION"
        if not path.is_file():
            continue
        text = path.read_text(encoding="utf-8").strip()
        if text:
            return text
    for root in roots:
        manifest = root / "manifest.json"
        if not manifest.is_file():
            continue
        try:
            data = json.loads(manifest.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            continue
        version = data.get("version") if isinstance(data, dict) else None
        if isinstance(version, str) and version.strip():
            return version.strip()
    return "0.0.0"


__version__ = _read_version()
