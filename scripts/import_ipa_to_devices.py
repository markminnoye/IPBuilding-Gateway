#!/usr/bin/env python3
"""Build or enrich devices.json from IP1100PoE autonomy EEPROM (.IPA) files.

Usage::

    python scripts/import_ipa_to_devices.py \\
        --ipa /path/to/10.10.1.55.IPA \\
        --output devices.ipa-draft.json \\
        --profile full

    python scripts/import_ipa_to_devices.py \\
        --ipa path/to/*.IPA \\
        --merge devices.json \\
        --output devices.merged.json

The input module IP is taken from the filename (``10.10.1.55.IPA``) unless
``--input-ip`` is set.  Target module types (relay/dimmer) are inferred from
the official installer IP ranges (§12.1 in IPBUILDING_KNOWLEDGE.md).

Autonomy func1/func2 mappings are written to ``import_report.md`` beside the
output file — they are not stored in devices.json (button logic belongs in HA).
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

_REPO_ROOT = Path(__file__).resolve().parents[1]
if str(_REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(_REPO_ROOT))

from gateway.installation import InstallationConfig, InstallationError
from gateway.ipa_parser import (
    build_devices_json_from_ipa,
    merge_devices_json,
    parse_ipa_file,
)


def _write_report(path: Path, ipa_paths: list[Path], drafts: list[dict]) -> None:
    lines = ["# IPA import report\n"]
    for ipa_path, draft in zip(ipa_paths, drafts, strict=True):
        lines.append(f"## {ipa_path.name}\n")
        input_mod = next(m for m in draft["modules"] if m["type"] == "input")
        lines.append(f"- Input module: `{input_mod['ip']}`")
        lines.append(f"- Pushbuttons: {len(input_mod.get('pushbuttons', []))}")
        targets = [m for m in draft["modules"] if m["type"] in ("relay", "dimmer")]
        lines.append(f"- Target modules: {len(targets)}")
        for mod in targets:
            chs = [c["ch"] for c in mod.get("channels", [])]
            lines.append(f"  - `{mod['ip']}` ({mod['type']}): channels {chs}")
        lines.append("")
        lines.append("### Autonomy hints (for HA import, not in devices.json)\n")
        parsed = parse_ipa_file(ipa_path)
        for btn in parsed.buttons:
            tgt_parts = [
                f"{t.ip} ch{t.channel}" for t in btn.targets
            ] or ["—"]
            lines.append(
                f"- `{btn.button_id}` port {btn.input_port} → {', '.join(tgt_parts)}"
            )
        lines.append("")
    path.write_text("\n".join(lines), encoding="utf-8")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--ipa",
        nargs="+",
        required=True,
        help="One or more .IPA files (input module IP from filename)",
    )
    parser.add_argument(
        "--output",
        default="devices.ipa-draft.json",
        help="Output devices.json path (default: devices.ipa-draft.json)",
    )
    parser.add_argument(
        "--merge",
        metavar="DEVICES_JSON",
        help="Optional existing devices.json to merge into (non-destructive)",
    )
    parser.add_argument(
        "--input-ip",
        help="Override input module IP when the filename has no dotted-quad",
    )
    parser.add_argument(
        "--profile",
        choices=("full", "conservative"),
        default="full",
        help="full = option B (all referenced channels active); "
        "conservative = one relay channel only",
    )
    args = parser.parse_args()

    ipa_paths = [Path(p) for p in args.ipa]
    draft: dict = {"modules": []}
    per_file_drafts: list[dict] = []

    for ipa_path in ipa_paths:
        if not ipa_path.exists():
            print(f"ERROR: IPA file not found: {ipa_path}", file=sys.stderr)
            return 1
        parsed = parse_ipa_file(ipa_path, input_ip=args.input_ip)
        file_draft = build_devices_json_from_ipa(parsed, profile=args.profile)
        per_file_drafts.append(file_draft)
        draft = merge_devices_json(draft, file_draft)

    if args.merge:
        merge_path = Path(args.merge)
        if not merge_path.exists():
            print(f"ERROR: merge file not found: {merge_path}", file=sys.stderr)
            return 1
        base = json.loads(merge_path.read_text(encoding="utf-8"))
        draft = merge_devices_json(base, draft)

    try:
        InstallationConfig._parse(draft)
    except InstallationError as exc:
        print(f"ERROR: generated document fails validation: {exc}", file=sys.stderr)
        return 2

    out_path = Path(args.output)
    out_path.write_text(
        json.dumps(draft, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )
    report_path = out_path.with_name(out_path.stem + ".import_report.md")
    _write_report(report_path, ipa_paths, per_file_drafts)

    mod_count = len(draft["modules"])
    btn_count = sum(
        len(m.get("pushbuttons", []))
        for m in draft["modules"]
        if m.get("type") == "input"
    )
    ch_count = sum(len(m.get("channels", [])) for m in draft["modules"])
    print(f"Wrote {out_path} ({mod_count} modules, {btn_count} pushbuttons, {ch_count} channels)")
    print(f"Report: {report_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
