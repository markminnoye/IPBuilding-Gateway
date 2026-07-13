#!/usr/bin/env python3
"""One-off migration: move devices.json's flat top-level "buttons" array
into modules[].pushbuttons[], and add an empty modules[].detectors[] to
every input module that doesn't already have one.

No field-bus calls — purely a file-format rewrite. Run once, before
upgrading to a gateway version whose InstallationConfig._parse() no
longer accepts the old flat "buttons" format.

Usage:
    python scripts/migrate_buttons_to_nested.py /path/to/devices.json

A backup of the original file is written alongside it as
"devices.json.bak" before any changes are made. Safe to re-run: a file
that has already been migrated (no top-level "buttons" key) is returned
unchanged.
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

log = logging.getLogger(__name__)


def migrate(raw: dict) -> dict:
    """Pure transform: old flat-buttons dict -> new nested-pushbuttons dict.

    Does not touch disk. ``raw["modules"]`` entries are shallow-copied
    before mutation so the caller's original dict is left untouched.
    """
    modules = [dict(m) for m in raw.get("modules", [])]
    by_mac = {m.get("mac"): m for m in modules if m.get("mac")}

    for module in modules:
        if module.get("type") == "input":
            module.setdefault("pushbuttons", [])
            module.setdefault("detectors", [])

    for btn in raw.get("buttons", []):
        module_id = btn.get("module_id")
        target = by_mac.get(module_id)
        if target is None:
            log.warning(
                "Skipping button %r: no matching module for module_id %r",
                btn.get("id"), module_id,
            )
            continue
        clean_btn = {k: v for k, v in btn.items() if k != "module_id"}
        target.setdefault("pushbuttons", []).append(clean_btn)
        target.setdefault("detectors", [])

    return {"modules": modules}


def migrate_file(path: str | Path) -> None:
    """Migrate a devices.json file in place, with a .bak backup first."""
    path = Path(path)
    if not path.exists():
        raise FileNotFoundError(f"devices.json not found at {path}")

    raw = json.loads(path.read_text(encoding="utf-8"))
    backup_path = path.with_suffix(path.suffix + ".bak")
    shutil.copyfile(path, backup_path)

    migrated = migrate(raw)
    path.write_text(json.dumps(migrated, indent=2) + "\n", encoding="utf-8")
    log.info("Migrated %s (backup at %s)", path, backup_path)


def main() -> int:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    if len(sys.argv) != 2:
        print(f"Usage: {sys.argv[0]} /path/to/devices.json", file=sys.stderr)
        return 1
    migrate_file(sys.argv[1])
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
