"""Canonical IPBuilding pushbutton hardware id.

Leaf module: imports nothing from ``gateway.*`` so ``payloads/`` can use it
without an import cycle.

The manufacturer's own key is four bytes (8 hex), as stored in the IPA
autonomy table. UDP ``B…E`` (14 hex) and HTTP ``getButtons`` (16 hex) wrap
the same four bytes; legacy IPA-derived configs used 10 hex (canonical +
target octet).
"""

from __future__ import annotations

_HEX = frozenset("0123456789abcdef")


def canonical_button_id(raw: str) -> str | None:
    """Return the 8-hex canonical id, or None when the input is not a known form.

    Dispatched on length after lowercasing and stripping whitespace:

    * 16 (getButtons, type prefix + wire) — strip 2 chars, then treat as 14
    * 14 (UDP wire) — ``s[0:6] + s[12:14]``
    * 10 (legacy IPA-derived config) — ``s[0:8]``
    * 8 (already canonical) — unchanged
    * other / non-hex — ``None``
    """
    if not raw:
        return None
    s = raw.strip().lower()
    if not s or any(c not in _HEX for c in s):
        return None
    n = len(s)
    if n == 16:
        s = s[2:]
        n = 14
    if n == 14:
        return s[0:6] + s[12:14]
    if n == 10:
        return s[0:8]
    if n == 8:
        return s
    return None
