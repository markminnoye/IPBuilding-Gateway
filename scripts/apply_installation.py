#!/usr/bin/env python3
"""Apply a devices.json draft via the gateway installation API.

Usage
-----
    python scripts/apply_installation.py \\
        --gateway http://127.0.0.1:8080 \\
        --mode merge_modules \\
        --file devices.import.json

    python scripts/apply_installation.py \\
        --gateway http://127.0.0.1:8080 \\
        --mode merge_modules \\
        --file devices.import.json \\
        --dry-run

Exit codes
----------
0  success
1  CLI / file error
2  validate/apply returned 422
3  gateway unreachable
"""

from __future__ import annotations

import argparse
import json
import sys
import urllib.error
import urllib.request
from pathlib import Path
from typing import Any


def _load_json(path: Path) -> dict[str, Any]:
    try:
        with open(path, encoding="utf-8") as fh:
            data = json.load(fh)
    except OSError as exc:
        print(f"ERROR: cannot read {path}: {exc}", file=sys.stderr)
        sys.exit(1)
    except json.JSONDecodeError as exc:
        print(f"ERROR: {path} is not valid JSON: {exc}", file=sys.stderr)
        sys.exit(1)
    if not isinstance(data, dict):
        print(f"ERROR: {path} must contain a JSON object", file=sys.stderr)
        sys.exit(1)
    return data


def _post_json(url: str, body: dict[str, Any]) -> tuple[int, dict[str, Any]]:
    payload = json.dumps(body).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            status = resp.status
            raw = resp.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        status = exc.code
        raw = exc.read().decode("utf-8", errors="replace")
    except urllib.error.URLError as exc:
        print(f"ERROR: gateway unreachable at {url}: {exc.reason}", file=sys.stderr)
        sys.exit(3)

    try:
        data = json.loads(raw) if raw else {}
    except json.JSONDecodeError:
        print(f"ERROR: non-JSON response ({status}): {raw[:200]}", file=sys.stderr)
        sys.exit(3)
    return status, data


def main() -> None:
    parser = argparse.ArgumentParser(description="Apply devices.json via gateway API")
    parser.add_argument("--gateway", required=True, help="Gateway base URL, e.g. http://127.0.0.1:8080")
    parser.add_argument("--mode", default="merge_modules",
                        choices=["replace", "merge_modules", "append_modules", "import_channels"])
    parser.add_argument("--file", required=True, type=Path, help="JSON file with modules[] (and optional buttons[])")
    parser.add_argument("--dry-run", action="store_true", help="POST /installation/validate only")
    args = parser.parse_args()

    doc = _load_json(args.file)
    body = {
        "mode": args.mode,
        "modules": doc.get("modules", []),
    }
    if "buttons" in doc:
        body["buttons"] = doc["buttons"]

    base = args.gateway.rstrip("/")
    endpoint = "validate" if args.dry_run else "apply"
    url = f"{base}/api/v1/installation/{endpoint}"

    status, result = _post_json(url, body)
    print(json.dumps(result, indent=2, ensure_ascii=False))

    if status == 422 or not result.get("ok", False):
        sys.exit(2)
    if status >= 400:
        sys.exit(3)
    sys.exit(0)


if __name__ == "__main__":
    main()
