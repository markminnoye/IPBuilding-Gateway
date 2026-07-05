#!/usr/bin/env python3
"""Standalone: import devices.json draft from legacy IPBuilding central (IP0000).

No gateway installation required. Fetches HTML from the mobile UI actions.php
and writes a local JSON file for review.

Usage:
    python import_from_legacy_central.py
    python import_from_legacy_central.py --central-host 10.10.1.1 --output devices.import.json
    python import_from_legacy_central.py --save-html legacy_raw.html
"""

from __future__ import annotations

import argparse
import json
import re
import sys
import urllib.error
import urllib.parse
import urllib.request
from pathlib import Path
from typing import Any
from urllib.parse import unquote

# ---------------------------------------------------------------------------
# HTML parser (legacy mobile UI)
# ---------------------------------------------------------------------------

_TOGGLE_RE = re.compile(
    r"protocolToggleItem[^\"']*?(?:ip=|')(\d+\.\d+\.\d+\.\d+)[^\"']*?(?:ch=|')(\d+)",
    re.IGNORECASE,
)
_DIM_RE = re.compile(
    r"protocolSetDimValue[^\"']*?(?:ip=|')(\d+\.\d+\.\d+\.\d+)[\"']?[^\"']*?(?:ch=|')(\d+)",
    re.IGNORECASE,
)
_ADRES_RE = re.compile(r"(\d+\.\d+\.\d+\.\d+)-(\d{2})")
_ITEM_RE = re.compile(
    r'<div[^>]*onclick="([^"]*(?:protocolToggleItem|protocolSetDimValue)[^"]*)"[^>]*>'
    r".*?contentItemDescr[^>]*>([^<]+)<.*?"
    r"(?:contentItemType|contentItemGroup)[^>]*>([^<]+)<",
    re.DOTALL | re.IGNORECASE,
)


def _decode_text(value: str) -> str:
    return unquote(value).strip()


def _channel_int(ch_str: str) -> int:
    return int(ch_str, 10)


def _extract_from_onclick(onclick: str) -> tuple[str, int, str] | None:
    dim = _DIM_RE.search(onclick)
    if dim:
        return dim.group(1), _channel_int(dim.group(2)), "dimmer"
    toggle = _TOGGLE_RE.search(onclick)
    if toggle:
        return toggle.group(1), _channel_int(toggle.group(2)), "relay"
    adres = _ADRES_RE.search(onclick)
    if adres:
        return adres.group(1), _channel_int(adres.group(2)), "relay"
    return None


def parse_legacy_central_html(html: str) -> dict[str, Any]:
    modules_by_ip: dict[str, dict[str, Any]] = {}

    for match in _ITEM_RE.finditer(html):
        onclick = match.group(1)
        parsed = _extract_from_onclick(onclick)
        if parsed is None:
            continue
        ip, ch, dev_type = parsed
        name = _decode_text(match.group(2)) or f"Ch {ch}"
        room = _decode_text(match.group(3))

        if ip not in modules_by_ip:
            modules_by_ip[ip] = {
                "name": ip,
                "ip": ip,
                "type": "relay",
                "firmware": "",
                "model": "",
                "mac": "",
                "channels": [],
            }
        mod = modules_by_ip[ip]
        if dev_type == "dimmer":
            mod["type"] = "dimmer"

        mod["channels"].append({
            "ch": ch,
            "name": name,
            "room": room or "Unconfigured",
            "semantic_type": "light",
            "active": False,
            "max_watt": 200 if mod["type"] == "dimmer" else 60,
        })

    modules = sorted(modules_by_ip.values(), key=lambda m: m["ip"])
    for mod in modules:
        mod["channels"].sort(key=lambda c: c["ch"])
        if mod["channels"]:
            mod["name"] = mod["channels"][0]["name"]

    return {"modules": modules}


# ---------------------------------------------------------------------------
# HTTP + CLI
# ---------------------------------------------------------------------------


def fetch_html(central_host: str, *, group: str | None, search: str) -> str:
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
        print(f"ERROR: cannot reach legacy central at {url}", file=sys.stderr)
        print(f"       Reason: {exc.reason}", file=sys.stderr)
        sys.exit(1)


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Import devices.json draft from legacy IPBuilding central (dry-run, local file only)",
    )
    parser.add_argument(
        "--central-host",
        default="10.10.1.1",
        help="IP address of the legacy centrale (default: 10.10.1.1)",
    )
    parser.add_argument(
        "--group",
        default=None,
        help="Optional: fetch one menu group via showGroupItems (exact name from mobile UI)",
    )
    parser.add_argument(
        "--search",
        default="",
        help="searchItems filter (default: empty = all items)",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("devices.import.json"),
        help="Output JSON file (default: devices.import.json in current folder)",
    )
    parser.add_argument(
        "--save-html",
        type=Path,
        default=None,
        help="Optional: also save the raw HTML response (for troubleshooting)",
    )
    args = parser.parse_args()

    print(f"Fetching legacy central HTML from {args.central_host} ...")
    html = fetch_html(args.central_host, group=args.group, search=args.search)

    if args.save_html:
        args.save_html.write_text(html, encoding="utf-8")
        print(f"Raw HTML saved to: {args.save_html}")

    doc = parse_legacy_central_html(html)
    if not doc.get("modules"):
        print("ERROR: no modules parsed from central HTML.", file=sys.stderr)
        print("       Save the HTML with --save-html and send it back for analysis.", file=sys.stderr)
        sys.exit(1)

    print(f"Parsed {len(doc['modules'])} module(s):")
    for mod in doc["modules"]:
        print(f"  - {mod['ip']:>15s}  {mod['type']:<7s}  ({len(mod['channels'])} channels)")

    args.output.write_text(
        json.dumps(doc, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    print(f"Written to: {args.output.resolve()}")
    print()
    print("Done. This script does NOT change the gateway — review the JSON file")
    print("and send it back to the project team for validation.")


if __name__ == "__main__":
    main()
