#!/usr/bin/env python3
"""Store name for the develop add-on and the stable release.

Home Assistant shows ``name`` and ``panel_title`` from
``ipbuilding_gateway/config.yaml`` on the git branch it tracks. The
develop image job writes "IPBuilding Gateway (develop)" onto develop.
A push to main writes "IPBuilding Gateway" back, and a release image
build does the same in its checkout before the image labels are read.

The description is the same on both channels and is not rewritten here.
"""

from __future__ import annotations

import argparse
import re
import sys
from pathlib import Path

STABLE_NAME = "IPBuilding Gateway"
DEVELOP_NAME = "IPBuilding Gateway (develop)"
DESCRIPTION = "Open IPBuilding field-bus gateway, replaces proprietary IPBox"

_NAME_RE = re.compile(r"^name:\s*.+$", re.MULTILINE)
_PANEL_RE = re.compile(r"^panel_title:\s*.+$", re.MULTILINE)

DEFAULT_CONFIG = Path("ipbuilding_gateway/config.yaml")


def channel_name(channel: str) -> str:
    if channel == "develop":
        return DEVELOP_NAME
    if channel == "stable":
        return STABLE_NAME
    raise ValueError(f"unknown channel {channel!r}")


def apply_channel(path: Path, channel: str) -> bool:
    """Set ``name`` and ``panel_title``. Returns True when the file changed."""
    name = channel_name(channel)
    text = path.read_text(encoding="utf-8")
    if _NAME_RE.search(text) is None:
        raise ValueError(f"no name field in {path}")
    if _PANEL_RE.search(text) is None:
        raise ValueError(f"no panel_title field in {path}")
    new_text = _NAME_RE.sub(f"name: {name}", text, count=1)
    new_text = _PANEL_RE.sub(f"panel_title: {name}", new_text, count=1)
    if new_text == text:
        return False
    path.write_text(new_text, encoding="utf-8")
    return True


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("channel", choices=("develop", "stable"))
    parser.add_argument("--config", type=Path, default=DEFAULT_CONFIG)
    args = parser.parse_args(argv)
    try:
        changed = apply_channel(args.config, args.channel)
    except ValueError as exc:
        print(str(exc), file=sys.stderr)
        return 1
    print("updated" if changed else "unchanged")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
