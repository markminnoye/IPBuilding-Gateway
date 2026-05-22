#!/usr/bin/env python3
"""Write captures/_local_push_pull_run_a.yaml from push_pull_run_a with your IPBox REST host.

Aligns:
  - settings.ipbox_base_url
  - settings.capture.bpf_filter (host list)
  - settings.correlate_extra_args (--verdict-profile relay, --rest-ip <host>)

Usage:
  IPBUILDING_IPBOX_REST_HOST=192.168.1.42 python3 scripts/prepare_local_push_pull_run_a_runbook.py
  python3 scripts/prepare_local_push_pull_run_a_runbook.py --host 192.168.1.42 -o captures/_local_push_pull_run_a.yaml

Optional:
  --verdict-pair   Append --verdict-pair 10.10.1.1,10.10.1.30 after relay profile.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError:
    print("PyYAML required (pip install -r requirements-capture.txt)", file=sys.stderr)
    raise SystemExit(2) from None

ARCHIVE_REST_HOST = "192.168.0.185"
DEFAULT_TEMPLATE = Path("resources_and_docs/workflows/push_pull_run_a_runbook.yaml")
DEFAULT_OUT = Path("captures/_local_push_pull_run_a.yaml")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host",
        default=os.environ.get("IPBUILDING_IPBOX_REST_HOST", "").strip(),
        help="IPBox REST address on home LAN (or set IPBUILDING_IPBOX_REST_HOST).",
    )
    parser.add_argument("--template", type=Path, default=DEFAULT_TEMPLATE)
    parser.add_argument("-o", "--output", type=Path, default=DEFAULT_OUT)
    parser.add_argument(
        "--verdict-pair",
        action="store_true",
        help="Add --verdict-pair 10.10.1.1,10.10.1.30 to correlate_extra_args.",
    )
    args = parser.parse_args()
    host = args.host
    if not host:
        print("Set --host or IPBUILDING_IPBOX_REST_HOST to your IPBox home-LAN IP.", file=sys.stderr)
        return 1

    tpl = args.template.resolve()
    if not tpl.is_file():
        print(f"Missing template: {tpl}", file=sys.stderr)
        return 1

    data = yaml.safe_load(tpl.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        print("Invalid runbook root", file=sys.stderr)
        return 1

    settings = data.setdefault("settings", {})
    if not isinstance(settings, dict):
        print("Invalid settings", file=sys.stderr)
        return 1

    settings["ipbox_base_url"] = f"http://{host}:30200/api/v1"

    cap = settings.setdefault("capture", {})
    if isinstance(cap, dict) and isinstance(cap.get("bpf_filter"), str):
        cap["bpf_filter"] = cap["bpf_filter"].replace(ARCHIVE_REST_HOST, host)

    extra: list[str] = ["--verdict-profile", "relay", "--rest-ip", host]
    if args.verdict_pair:
        extra.extend(["--verdict-pair", "10.10.1.1,10.10.1.30"])
    settings["correlate_extra_args"] = extra

    out = args.output
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(yaml.safe_dump(data, sort_keys=False, allow_unicode=True), encoding="utf-8")
    print(f"Wrote {out}")
    print("Run: ./scripts/relay_run_a_capture.sh --interface en7 --runbook", out)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
