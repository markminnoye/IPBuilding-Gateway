"""Run a captured frame through the gateway decoders. No network."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any


def ensure_import_paths() -> None:
    """Make ``gateway`` importable from the repo or from a packed bundle."""
    here = Path(__file__).resolve()
    toolkit_root = here.parents[1]
    candidates = [toolkit_root]
    if len(here.parents) > 2:
        candidates.append(here.parents[2])
    for path in candidates:
        if (path / "gateway").is_dir() and str(path) not in sys.path:
            sys.path.insert(0, str(path))


def parse_frame(payload: str) -> bytes:
    """Accept hex (``5330303030``) or a short ASCII token (``S0000``)."""
    text = (payload or "").strip()
    if not text:
        raise ValueError("empty")
    compact = "".join(text.split())
    if len(compact) >= 2 and len(compact) % 2 == 0:
        try:
            return bytes.fromhex(compact)
        except ValueError:
            pass
    try:
        return text.encode("ascii")
    except UnicodeEncodeError as exc:
        raise ValueError("not-hex-or-ascii") from exc


def decode_frame(data: bytes) -> dict[str, Any]:
    """Try every field-bus decoder. A miss is ``matched: false``, not an error."""
    ensure_import_paths()
    from gateway.payloads.dimmer import decode_dimmer_payload
    from gateway.payloads.input import decode_input_payload
    from gateway.payloads.relay import decode_relay_payload

    attempts = [
        ("relay", decode_relay_payload(data)),
        ("dimmer", decode_dimmer_payload(data)),
        ("input", decode_input_payload(data)),
    ]
    matches = [
        {"decoder": name, "fields": fields}
        for name, fields in attempts
        if fields is not None
    ]
    ascii_text: str | None
    try:
        ascii_text = data.decode("ascii")
    except UnicodeDecodeError:
        ascii_text = None
    return {
        "hex": data.hex(),
        "ascii": ascii_text,
        "length": len(data),
        "matched": bool(matches),
        "matches": matches,
    }
