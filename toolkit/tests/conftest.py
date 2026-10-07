"""Make toolkit imports work no matter which directory pytest starts from."""

from __future__ import annotations

import sys
from pathlib import Path

_TESTS = Path(__file__).resolve().parent
_TOOLKIT = _TESTS.parent
_REPO = _TOOLKIT.parent
for _path in (_TESTS, _TOOLKIT, _REPO):
    text = str(_path)
    if text not in sys.path:
        sys.path.insert(0, text)
