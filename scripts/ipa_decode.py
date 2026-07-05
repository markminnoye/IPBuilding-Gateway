#!/usr/bin/env python3
"""Decode IPBuilding .IPA autonomy EEPROM exports.

Hypothesis (operator-confirmed for 10.10.1.55.IPA):
  tail bytes [octet][ch_hi][ch_lo] map to target 10.10.1.<octet> and a
  1-based relay/dimmer channel (ASCII digits in the last two bytes).

Special tails ``42 xx FF`` are global actions (B-family), not relay maps.

Usage:
  python scripts/ipa_decode.py path/to/10.10.1.55.IPA --csv out.csv --json out.json
  python scripts/ipa_decode.py path/to/10.10.1.55.IPA --devices-json draft.json
"""

from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from pathlib import Path

DEFAULT_SUBNET = "10.10.1"

FIELDNAMES = [
    "record_index",
    "input_module_ip",
    "button_id_hex",
    "target_ip",
    "target_channel",
    "target_channel_raw",
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
    if 0x30 <= v <= 0x39:
        # ASCII digit only — ambiguous; common relay octet 30 stored as 0x30
        if byte_hex == "30":
            return 30
        if byte_hex == "32":
            return 32
        if byte_hex == "40":
            return 40
        return v - 0x30
    if 1 <= v <= 254:
        return v
    return None


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
                "button_id_hex": "".join(rec).lower(),
                "target_ip": "",
                "target_channel": "",
                "target_channel_raw": "",
                "action_code": "incomplete",
                "notes": f"short record ({len(rec)} bytes)",
            })
            continue

        button_id = "".join(rec[:4]).lower()
        tail = rec[4:]

        if len(tail) >= 3 and tail[0] == "42" and tail[-1] == "FF":
            sub = int(tail[1], 16) if len(tail) >= 2 else 0
            rows.append({
                "record_index": idx,
                "input_module_ip": input_ip,
                "button_id_hex": button_id,
                "target_ip": "",
                "target_channel": "",
                "target_channel_raw": "",
                "action_code": f"B{sub:02X}",
                "notes": "global/special action (no relay channel tail)",
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
            rows.append({
                "record_index": idx,
                "input_module_ip": input_ip,
                "button_id_hex": button_id,
                "target_ip": f"{subnet}.{octet}" if octet is not None else "",
                "target_channel": channel,
                "target_channel_raw": channel_raw,
                "action_code": "map",
                "notes": "",
            })
            continue

        rows.append({
            "record_index": idx,
            "input_module_ip": input_ip,
            "button_id_hex": button_id,
            "target_ip": "",
            "target_channel": "",
            "target_channel_raw": "",
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
        chs = sorted({
            int(r["target_channel"])
            for r in rows
            if r.get("target_ip") == tip and r.get("target_channel") not in ("", None)
        })
        max_ch = max(chs) if chs else 0
        # Heuristic: <=8 and not only channel 0 → dimmer; else relay.
        mod_type = "dimmer" if max_ch >= 1 and max_ch <= 8 else "relay"
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
    return {
        "@context": {
            "@vocab": "https://github.com/markminnoye/IPBuilding-Gateway/ipa#",
            "inputModule": "inputModule",
            "buttonId": "buttonId",
            "targetModule": "targetModule",
            "targetChannel": "targetChannel",
            "actionCode": "actionCode",
        },
        "type": "AutonomyTable",
        "inputModule": input_ip,
        "subnet": subnet,
        "sourceFile": path.name,
        "mappingCount": len(rows),
        "mappings": [
            {
                "type": "AutonomyMapping",
                "recordIndex": r["record_index"],
                "buttonId": r["button_id_hex"],
                "targetModule": r["target_ip"] or None,
                "targetChannel": r["target_channel"] if r["target_channel"] != "" else None,
                "targetChannelRaw": r["target_channel_raw"] or None,
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


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("ipa", type=Path, help="Path to .IPA file (binary or hex text dump)")
    parser.add_argument("--subnet", default=DEFAULT_SUBNET, help=f"Subnet prefix (default {DEFAULT_SUBNET})")
    parser.add_argument("--csv", type=Path, help="Write CSV output")
    parser.add_argument("--json", type=Path, help="Write JSON-LD output")
    parser.add_argument("--devices-json", type=Path, help="Write devices.json draft only")
    args = parser.parse_args(argv)

    if not args.ipa.is_file():
        parser.error(f"file not found: {args.ipa}")

    input_ip = input_ip_from_path(args.ipa)
    records = load_ipa(args.ipa)
    rows = decode_ipa_records(records, input_ip=input_ip, subnet=args.subnet)

    if not args.csv and not args.json and not args.devices_json:
        args.csv = args.ipa.with_suffix(".decoded.csv")
        args.json = args.ipa.with_suffix(".decoded.json")

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
