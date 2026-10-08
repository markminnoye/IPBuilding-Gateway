"""Random installation id for a debug report.

Generated once with UUID4 and stored next to the local toolkit config.
It is never derived from a serial number, address, MAC address, or name.
"""

from __future__ import annotations

import os
import uuid
from pathlib import Path


def installation_id_path() -> Path:
    override = os.environ.get("IPBUILDING_INSTALLATION_ID_FILE", "").strip()
    if override:
        return Path(override)
    return Path.home() / ".config" / "ipbuilding-gateway-tools" / "installation_id"


def installation_id() -> str:
    """Return the stored UUID4, or create one."""
    path = installation_id_path()
    existing = _read_uuid4(path)
    if existing:
        return existing
    value = str(uuid.uuid4())
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(value + "\n", encoding="utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return value


def _read_uuid4(path: Path) -> str:
    if not path.is_file():
        return ""
    text = path.read_text(encoding="utf-8").strip()
    try:
        parsed = uuid.UUID(text)
    except ValueError:
        return ""
    if parsed.version != 4:
        return ""
    return str(parsed)
