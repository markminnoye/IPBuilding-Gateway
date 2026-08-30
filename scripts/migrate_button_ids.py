#!/usr/bin/env python3
"""Rewrite devices.json pushbutton ids to the canonical 8-hex form.

10-hex (legacy IPA-derived), 14-hex (UDP wire) and 16-hex (getButtons)
ids become 8 hex. Names, rooms, active flags and everything else are
left unchanged. No field-bus calls — purely a file-format rewrite.

Usage:
    python scripts/migrate_button_ids.py /path/to/devices.json

A backup of the original file is written alongside it as
"devices.json.bak" before any changes are made. Safe to re-run: a file
that is already canonical is rewritten identically (backup still made).
"""

from __future__ import annotations

import json
import logging
import shutil
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parent.parent
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gateway.button_id import canonical_button_id  # noqa: E402

log = logging.getLogger(__name__)


def migrate(raw: dict) -> dict:
    """Pure transform: rewrite pushbutton ids to canonical 8-hex.

    Does not touch disk. ``raw["modules"]`` entries are shallow-copied
    before mutation so the caller's original dict is left untouched.
    Reports per-module conversion counts and warns on canonical collisions.
    """
    modules = [dict(m) for m in raw.get("modules", [])]
    for module in modules:
        if module.get("type") != "input":
            continue
        buttons = [dict(b) for b in module.get("pushbuttons", [])]
        converted = 0
        seen: dict[str, str] = {}
        kept: list[dict] = []
        for btn in buttons:
            raw_id = str(btn.get("id", ""))
            canonical = canonical_button_id(raw_id)
            if canonical is None:
                log.warning(
                    "Module %s: skipping unrecognised pushbutton id %r",
                    module.get("ip"),
                    raw_id,
                )
                kept.append(btn)
                continue
            if canonical in seen and seen[canonical] != raw_id.strip().lower():
                log.warning(
                    "Module %s: canonical collision %s (raw %r vs %r); keeping first",
                    module.get("ip"),
                    canonical,
                    seen[canonical],
                    raw_id,
                )
                continue
            if canonical not in seen:
                seen[canonical] = raw_id.strip().lower()
            if canonical != raw_id.strip().lower():
                converted += 1
            btn["id"] = canonical
            kept.append(btn)
        module["pushbuttons"] = kept
        log.info(
            "Module %s: %d pushbutton id(s) converted to 8-hex (%d kept)",
            module.get("ip"),
            converted,
            len(kept),
        )
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
