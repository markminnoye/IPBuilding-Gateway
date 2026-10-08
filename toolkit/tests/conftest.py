"""Make toolkit imports work no matter which directory pytest starts from."""

from __future__ import annotations

import sys
from pathlib import Path

import pytest

_TESTS = Path(__file__).resolve().parent
_TOOLKIT = _TESTS.parent
_REPO = _TOOLKIT.parent
for _path in (_TESTS, _TOOLKIT, _REPO):
    text = str(_path)
    if text not in sys.path:
        sys.path.insert(0, text)


@pytest.fixture(autouse=True)
def installation_id_file(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Keep the random installation id out of the real home directory."""
    path = tmp_path / "installation_id"
    monkeypatch.setenv("IPBUILDING_INSTALLATION_ID_FILE", str(path))
    return path
