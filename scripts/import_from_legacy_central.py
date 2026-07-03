#!/usr/bin/env python3
"""Import devices.json draft from a legacy IPBuilding central (IP0000 / mobile UI).

Fetches component list HTML from ``actions.php`` (``searchItems`` or
``showGroupItems``) and maps ``Adres`` (``ip-ch``) + descriptions to the
open gateway ``devices.json`` schema.

Usage
-----
    python scripts/import_from_legacy_central.py \\
        --central-host 10.10.1.1 \\
        --output devices.import.json

    python scripts/import_from_legacy_central.py \\
        --central-host 10.10.1.1 \\
        --apply http://127.0.0.1:8080 \\
        --mode merge_modules

Exit codes
----------
0  success
1  extract / HTTP error
2  validate/apply 422 (when --apply is used)
3  gateway unreachable (when --apply is used)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path

from scripts.legacy_central_parser import parse_legacy_central_html


def _fetch_html(central_host: str, *, group: str | None, search: str) -> str:
    base = f"http://{central_host}/mobile/core/actions.php"
    if group:
        params = {"methode": "showGroupItems", "groupId": group}
    else:
        params = {"methode": "searchItems", "searchStr": search}
    url = f"{base}?{urllib.parse.urlencode(params)}"
    try:
        with urllib.request.urlopen(url, timeout=30) as resp:
            return resp.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"ERROR: cannot reach legacy central at {url}: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import devices.json from legacy IPBuilding central mobile UI",
    )
    parser.add_argument("--central-host", default="10.10.1.1")
    parser.add_argument("--group", default=None, help="Fetch showGroupItems for this group name")
    parser.add_argument("--search", default="", help="searchItems query (default: all items)")
    parser.add_argument("--output", type=Path, default=Path("devices.import.json"))
    parser.add_argument("--apply", metavar="GATEWAY_URL", help="Apply via gateway after extract")
    parser.add_argument("--mode", default="merge_modules",
                        choices=["replace", "merge_modules", "append_modules", "import_channels"])
    parser.add_argument("--dry-run", action="store_true", help="With --apply: validate only")
    args = parser.parse_args()

    print(f"Fetching legacy central HTML from {args.central_host}...")
    html = _fetch_html(args.central_host, group=args.group, search=args.search)
    doc = parse_legacy_central_html(html)

    if not doc.get("modules"):
        print("ERROR: no modules parsed from central HTML", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(doc['modules'])} module(s):")
    for mod in doc["modules"]:
        print(f"  - {mod['ip']:>15s}  {mod['type']:<7s}  ({len(mod['channels'])} channels)")

    args.output.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Written to: {args.output}")

    if not args.apply:
        return

    cmd = [
        sys.executable,
        str(Path(__file__).resolve().parent / "apply_installation.py"),
        "--gateway", args.apply,
        "--mode", args.mode,
        "--file", str(args.output),
    ]
    if args.dry_run:
        cmd.append("--dry-run")
    result = subprocess.run(cmd, check=False)
    sys.exit(result.returncode)


if __name__ == "__main__":
    main()
