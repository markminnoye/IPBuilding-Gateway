#!/usr/bin/env python3
"""Decode IPBuilding .IPA autonomy EEPROM exports.

Record layout (hypothesis, validated on 10.10.1.55.IPA from tester install):

  Channel map:  [button_id x4][target_octet][ch_hi][ch_lo]
                → 10.10.1.<octet> + 1-based channel; implied action toggle.

  Global action: [button_id x4][0x42]['0'|'1'|'2'][0xFF]
                → per install manual §12.4: Toggle / All on / All off.

There is no known HTTP URL to download .IPA from field modules; files are
generated on the legacy central by ``buttonIP1100.exe`` (see
``IPBUILDING_KNOWLEDGE.md`` §12.5). Closest module HTTP read: ``getButtons``.

Usage:
  python scripts/ipa_decode.py path/to/10.10.1.55.IPA --csv out.csv --json out.json
  python scripts/ipa_decode.py path/to/10.10.1.55.IPA --devices-json draft.json
  python scripts/ipa_decode.py path/to/10.10.1.55.IPA --output-dir ./out
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_SUBNET = "10.10.1"

# Install manual §12.4 ordering: Toggle / All on / All off (indices 0/1/2).
GLOBAL_ACTION_LABELS: dict[int, str] = {
    0: "toggle",
    1: "all_on",
    2: "all_off",
}

FIELDNAMES = [
    "record_index",
    "input_module_ip",
    "record_type",
    "button_id_hex",
    "target_ip",
    "target_module_type",
    "target_channel",
    "target_channel_raw",
    "action_index",
    "action_label",
    "action_code",
    "notes",
]


def _parse_hex_dump_text(text: str) -> list[list[str]]:
    lines = [ln.strip().upper() for ln in text.splitlines() if ln.strip()]
    records: list[list[str]] = []
    cur: list[str] = []
    for line in lines:
        if line == "T":
            if cur:
                records.append(cur)
                cur = []
        else:
            cur.append(line)
    if cur:
        records.append(cur)
    return records


def _parse_binary_ipa(data: bytes) -> list[list[str]]:
    records: list[list[str]] = []
    cur: list[str] = []
    for b in data:
        if b == ord("T"):
            if cur:
                records.append(cur)
                cur = []
        else:
            cur.append(f"{b:02X}")
    if cur:
        records.append(cur)
    return records


def input_ip_from_path(path: Path) -> str:
    m = re.search(r"(\d+\.\d+\.\d+\.\d+)", path.stem)
    return m.group(1) if m else "unknown"


def _target_octet(byte_hex: str) -> int | None:
    v = int(byte_hex, 16)
    if byte_hex == "30":
        return 30
    if byte_hex == "32":
        return 32
    if byte_hex == "40":
        return 40
    if 0x30 <= v <= 0x39:
        return v - 0x30
    if 1 <= v <= 254:
        return v
    return None


def _module_type_for_octet(octet: int | None, channel: int | str) -> str:
    if octet is None:
        return ""
    if octet == 40:
        return "dimmer"
    if octet == 30:
        return "relay"
    ch = int(channel) if str(channel).isdigit() else 0
    if 1 <= ch <= 8:
        return "dimmer?"
    if ch >= 9:
        return "relay?"
    return "unknown"


def decode_ipa_records(
    records: list[list[str]],
    *,
    input_ip: str,
    subnet: str = DEFAULT_SUBNET,
) -> list[dict[str, object]]:
    rows: list[dict[str, object]] = []
    for idx, rec in enumerate(records, start=1):
        if all(b == "FF" for b in rec):
            continue

        if len(rec) < 4:
            rows.append({
                "record_index": idx,
                "input_module_ip": input_ip,
                "record_type": "incomplete",
                "button_id_hex": "".join(rec).lower(),
                "target_ip": "",
                "target_module_type": "",
                "target_channel": "",
                "target_channel_raw": "",
                "action_index": "",
                "action_label": "",
                "action_code": "incomplete",
                "notes": f"short record ({len(rec)} bytes)",
            })
            continue

        button_id = "".join(rec[:4]).lower()
        tail = rec[4:]

        if len(tail) >= 3 and tail[0] == "42" and tail[-1] == "FF":
            action_byte = int(tail[1], 16) if len(tail) >= 2 else 0
            action_index = action_byte - 0x30 if 0x30 <= action_byte <= 0x39 else action_byte
            action_label = GLOBAL_ACTION_LABELS.get(
                action_index,
                f"unknown_global_{action_index}",
            )
            rows.append({
                "record_index": idx,
                "input_module_ip": input_ip,
                "record_type": "global_action",
                "button_id_hex": button_id,
                "target_ip": "",
                "target_module_type": "",
                "target_channel": "",
                "target_channel_raw": "",
                "action_index": action_index,
                "action_label": action_label,
                "action_code": f"B{action_index}",
                "notes": (
                    "global action (install manual §12.4: toggle / all on / all off); "
                    "label mapping is hypothesis — not wire-RE'd on IPA"
                ),
            })
            continue

        if len(tail) >= 3:
            octet = _target_octet(tail[0])
            ch_chars = []
            for b in tail[1:3]:
                v = int(b, 16)
                if 0x30 <= v <= 0x39:
                    ch_chars.append(chr(v))
            channel_raw = "".join(ch_chars)
            channel: int | str = int(channel_raw) if channel_raw.isdigit() else ""
            mod_type = _module_type_for_octet(octet, channel)
            rows.append({
                "record_index": idx,
                "input_module_ip": input_ip,
                "record_type": "channel_map",
                "button_id_hex": button_id,
                "target_ip": f"{subnet}.{octet}" if octet is not None else "",
                "target_module_type": mod_type,
                "target_channel": channel,
                "target_channel_raw": channel_raw,
                "action_index": "",
                "action_label": "toggle",
                "action_code": "map",
                "notes": (
                    "single target channel; IPA has no per-map action byte — "
                    "toggle assumed. Dimmer level / ramp not visible in IPA binary "
                    "(see getButtons func1/func2 for richer actions)"
                ),
            })
            continue

        rows.append({
            "record_index": idx,
            "input_module_ip": input_ip,
            "record_type": "unknown",
            "button_id_hex": button_id,
            "target_ip": "",
            "target_module_type": "",
            "target_channel": "",
            "target_channel_raw": "",
            "action_index": "",
            "action_label": "",
            "action_code": "unknown",
            "notes": f"unparsed tail: {' '.join(tail)}",
        })

    return rows


def devices_json_draft(
    input_ip: str,
    rows: list[dict[str, object]],
    *,
    subnet: str = DEFAULT_SUBNET,
) -> dict[str, object]:
    target_ips = sorted({str(r["target_ip"]) for r in rows if r.get("target_ip")})
    modules: list[dict[str, object]] = [
        {
            "name": "IP1100PoE",
            "ip": input_ip,
            "type": "input",
            "model": "IP1100PoE",
            "mac": "",
            "firmware": "",
            "channels": [],
            "active": False,
        }
    ]

    for tip in target_ips:
        ch_rows = [
            r for r in rows
            if r.get("target_ip") == tip and r.get("record_type") == "channel_map"
        ]
        chs = sorted({
            int(r["target_channel"])
            for r in ch_rows
            if r.get("target_channel") not in ("", None)
        })
        types = {str(r.get("target_module_type", "")) for r in ch_rows}
        if "dimmer" in types:
            mod_type = "dimmer"
        elif "relay" in types:
            mod_type = "relay"
        else:
            max_ch = max(chs) if chs else 0
            mod_type = "dimmer" if 1 <= max_ch <= 8 else "relay"
        model = "IP0300PoE" if mod_type == "dimmer" else "IP0200PoE"
        modules.append({
            "name": model,
            "ip": tip,
            "type": mod_type,
            "model": model,
            "mac": "",
            "firmware": "",
            "channels": [
                {
                    "ch": c if c == 0 else c - 1,
                    "name": f"ch{c}",
                    "room": "Unconfigured",
                    "semantic_type": "light",
                    "active": False,
                    "max_watt": 200 if mod_type == "dimmer" else 60,
                }
                for c in chs
            ],
            "active": False,
        })

    return {"modules": modules}


def json_ld_document(
    path: Path,
    input_ip: str,
    rows: list[dict[str, object]],
    *,
    subnet: str = DEFAULT_SUBNET,
) -> dict[str, object]:
    global_counts: dict[str, int] = {}
    for r in rows:
        if r.get("record_type") == "global_action":
            label = str(r.get("action_label", ""))
            global_counts[label] = global_counts.get(label, 0) + 1

    return {
        "@context": {
            "@vocab": "https://github.com/markminnoye/IPBuilding-Gateway/ipa#",
            "inputModule": "inputModule",
            "buttonId": "buttonId",
            "targetModule": "targetModule",
            "targetChannel": "targetChannel",
            "actionLabel": "actionLabel",
        },
        "type": "AutonomyTable",
        "inputModule": input_ip,
        "subnet": subnet,
        "sourceFile": path.name,
        "mappingCount": len(rows),
        "globalActionCounts": global_counts,
        "mappings": [
            {
                "type": "AutonomyMapping",
                "recordIndex": r["record_index"],
                "recordType": r["record_type"],
                "buttonId": r["button_id_hex"],
                "targetModule": r["target_ip"] or None,
                "targetModuleType": r["target_module_type"] or None,
                "targetChannel": r["target_channel"] if r["target_channel"] != "" else None,
                "targetChannelRaw": r["target_channel_raw"] or None,
                "actionIndex": r["action_index"] if r["action_index"] != "" else None,
                "actionLabel": r["action_label"] or None,
                "actionCode": r["action_code"],
                "notes": r["notes"] or None,
            }
            for r in rows
        ],
        "devicesJsonDraft": devices_json_draft(input_ip, rows, subnet=subnet),
    }


def load_ipa(path: Path) -> list[list[str]]:
    data = path.read_bytes()
    if b"\n" in data[:4096] or data[:4].strip().isascii():
        return _parse_hex_dump_text(data.decode("utf-8", errors="replace"))
    return _parse_binary_ipa(data)


def default_output_paths(ipa_path: Path, output_dir: Path | None) -> tuple[Path, Path, Path]:
    stem = ipa_path.stem
    if re.search(r"\d+\.\d+\.\d+\.\d+", stem):
        base = stem
    else:
        base = stem
    parent = output_dir if output_dir is not None else ipa_path.parent
    parent.mkdir(parents=True, exist_ok=True)
    return (
        parent / f"{base}.decoded.csv",
        parent / f"{base}.decoded.json",
        parent / f"{base}.devices_draft.json",
    )


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path, help="Path to .IPA file (binary or hex text dump)")
    parser.add_argument("--subnet", default=DEFAULT_SUBNET, help=f"Subnet prefix (default {DEFAULT_SUBNET})")
    parser.add_argument("--output-dir", type=Path, help="Directory for default output filenames")
    parser.add_argument("--csv", type=Path, help="Write CSV output")
    parser.add_argument("--json", type=Path, help="Write JSON-LD output")
    parser.add_argument("--devices-json", type=Path, help="Write devices.json draft only")
    args = parser.parse_args(argv)

    if not args.ipa.is_file():
        parser.error(f"file not found: {args.ipa}")

    input_ip = input_ip_from_path(args.ipa)
    records = load_ipa(args.ipa)
    rows = decode_ipa_records(records, input_ip=input_ip, subnet=args.subnet)

    default_csv, default_json, default_devices = default_output_paths(args.ipa, args.output_dir)
    if not args.csv and not args.json and not args.devices_json:
        args.csv = default_csv
        args.json = default_json
        args.devices_json = default_devices

    if args.csv:
        with args.csv.open("w", newline="", encoding="utf-8") as f:
            w = csv.DictWriter(f, fieldnames=FIELDNAMES)
            w.writeheader()
            w.writerows(rows)
        print(f"Wrote CSV ({len(rows)} rows): {args.csv}", file=sys.stderr)

    if args.json:
        doc = json_ld_document(args.ipa, input_ip, rows, subnet=args.subnet)
        args.json.write_text(json.dumps(doc, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote JSON-LD: {args.json}", file=sys.stderr)

    if args.devices_json:
        draft = devices_json_draft(input_ip, rows, subnet=args.subnet)
        args.devices_json.write_text(json.dumps(draft, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote devices.json draft: {args.devices_json}", file=sys.stderr)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
