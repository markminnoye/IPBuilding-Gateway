"""Toolkit version. Test builds use 0.1.0-rc.N. A release tag must match toolkit/VERSION."""

from __future__ import annotations

from pathlib import Path

def _read_version() -> str:
    path = Path(__file__).resolve().parents[1] / "VERSION"
    if path.is_file():
        return path.read_text(encoding="utf-8").strip()
    return "0.0.0"


__version__ = _read_version()
