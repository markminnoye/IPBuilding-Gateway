#!/usr/bin/env python3
"""Timing analysis for relay `P000000000` (`relay_reply_candidate`) vs hub→relay commands.

Reads `udp_ipbox_export.txt` from correlate_capture_session.py (UDP table lines) or runs
tshark on a session PCAP (same host filter as correlate).

Example:
  python3 scripts/analyze_relay_reply_candidate_timing.py \\
    captures/2026-05-05T1040Z_user-full-capture/udp_ipbox_export.txt
  python3 scripts/analyze_relay_reply_candidate_timing.py captures/2026-05-05T1040Z_user-full-capture \\
    --rest-ip 192.168.0.185
"""

from __future__ import annotations

import argparse
import json
import statistics
import sys
import tempfile
from ast import literal_eval
from collections import Counter
from pathlib import Path

from relay_payload_parser import parse_relay_payload_ascii

try:
    from correlate_capture_session import payload_hex_to_ascii, tshark_rows
except ImportError:  # pragma: no cover
    tshark_rows = None  # type: ignore[misc, assignment]
    payload_hex_to_ascii = None  # type: ignore[misc, assignment]


def _rows_from_export(path: Path) -> list[tuple[float, str, str, str, dict[str, object] | None]]:
    text = path.read_text(encoding="utf-8", errors="replace")
    rows: list[tuple[float, str, str, str, dict[str, object] | None]] = []
    in_udp = False
    for line in text.splitlines():
        if line.startswith("## UDP"):
            in_udp = True
            continue
        if not in_udp or not line.strip() or line.startswith("#"):
            continue
        if line.startswith("- ") or line.startswith("STATUS"):
            break
        parts = line.split("\t")
        if len(parts) < 9:
            continue
        epoch_s, src, dst = parts[0], parts[2], parts[4]
        asc_repr = parts[7]
        rest = "\t".join(parts[8:]).strip()
        try:
            asc = literal_eval(asc_repr)
        except (SyntaxError, ValueError):
            continue
        if not isinstance(asc, str):
            continue
        try:
            epoch = float(epoch_s)
        except ValueError:
            continue
        parsed: dict[str, object] | None = None
        if rest.startswith("{"):
            try:
                parsed = json.loads(rest)
            except json.JSONDecodeError:
                parsed = None
        rows.append((epoch, src, dst, asc, parsed))
    return rows


def _rows_from_pcap(
    pcap: Path, *, rest_ip: str
) -> list[tuple[float, str, str, str, dict[str, object] | None]]:
    if tshark_rows is None or payload_hex_to_ascii is None:
        raise RuntimeError("correlate_capture_session import failed")
    raw_rows = tshark_rows(pcap, rest_ip=rest_ip)
    out: list[tuple[float, str, str, str, dict[str, object] | None]] = []
    for epoch_s, _trel, src, _sport, dst, _dport, pl_hex in raw_rows:
        asc = payload_hex_to_ascii(pl_hex)
        parsed_obj = parse_relay_payload_ascii(asc)
        parsed: dict[str, object] | None = parsed_obj if isinstance(parsed_obj, dict) else None
        try:
            epoch = float(epoch_s)
        except ValueError:
            continue
        out.append((epoch, src, dst, asc, parsed))
    return out


def analyze(
    rows: list[tuple[float, str, str, str, dict[str, object] | None]],
    *,
    hub_ip: str,
    relay_ip: str,
) -> dict[str, object]:
    cmds: list[tuple[float, str, dict[str, object]]] = []
    for epoch, src, dst, _asc, pj in rows:
        if src != hub_ip or dst != relay_ip or not pj:
            continue
        if pj.get("family") == "relay_command":
            cmds.append((epoch, str(pj.get("action", "")), pj))

    p9_events: list[tuple[float, str, str, dict[str, object] | None]] = []
    for epoch, src, dst, _asc, pj in rows:
        if src != relay_ip or not pj:
            continue
        if pj.get("family") != "relay_reply_candidate":
            continue
        p9_events.append((epoch, src, dst, pj))

    deltas_ms: list[float] = []
    after_action: list[str] = []
    missing_prior = 0
    for epoch, _src, _dst, pj in p9_events:
        prior = [c for c in cmds if c[0] < epoch]
        if not prior:
            missing_prior += 1
            continue
        last_e, last_action, _ = prior[-1]
        dt_s = epoch - last_e
        deltas_ms.append(dt_s * 1000.0)
        after_action.append(last_action)

    summary: dict[str, object] = {
        "relay_reply_candidate_frames": len(p9_events),
        "hub_to_relay_relay_command_frames": len(cmds),
        "p9_with_prior_hub_command": len(deltas_ms),
        "p9_without_prior_hub_command_in_export": missing_prior,
        "delta_ms_prior_relay_command": deltas_ms,
        "prior_relay_command_actions": after_action,
    }
    if deltas_ms:
        summary["delta_ms_median"] = statistics.median(deltas_ms)
        summary["delta_ms_min"] = min(deltas_ms)
        summary["delta_ms_max"] = max(deltas_ms)
    return summary


def _emit_report(data: dict[str, object], file=sys.stdout) -> None:
    print("relay_reply_candidate (P000000000) timing report", file=file)
    for k in sorted(data):
        if k.startswith("prior_"):
            continue
        print(f"  {k}: {data[k]}", file=file)
    acts = data.get("prior_relay_command_actions")
    if isinstance(acts, list) and acts:
        print("  prior relay_command action histogram:", file=file)
        for a, c in Counter(str(x) for x in acts).most_common():
            print(f"    {a!r}: {c}", file=file)


def _self_test() -> int:
    body = r"""
## UDP (epoch  t_rel_s  src  sport  dst  dport  payload_hex  payload_ascii  payload_parse)
1000.0\t0\t10.10.1.1\t50445\t10.10.1.30\t1001\tx\t'P0000'\t{"family":"relay_command","action":"pulse"}
1000.002\t0\t10.10.1.30\t1001\t10.10.1.1\t50445\tx\t'P000000000'\t{"family":"relay_reply_candidate"}
""".replace(
        "\\t", "\t"
    )
    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False, encoding="utf-8") as f:
        f.write("# fixture\n" + body)
        name = f.name
    try:
        rows = _rows_from_export(Path(name))
        data = analyze(rows, hub_ip="10.10.1.1", relay_ip="10.10.1.30")
    finally:
        Path(name).unlink(missing_ok=True)
    med = data.get("delta_ms_median")
    if med is None or not (1.0 < float(med) < 5.0):
        print(f"self-test: expected median delta ~2ms, got {med!r}", file=sys.stderr)
        return 1
    print("self-test ok")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "path",
        type=Path,
        nargs="?",
        help="udp_ipbox_export.txt or session directory containing capture.pcapng",
    )
    parser.add_argument("--hub-ip", default="10.10.1.1")
    parser.add_argument("--relay-ip", default="10.10.1.30")
    parser.add_argument("--rest-ip", default="192.168.0.185")
    parser.add_argument("--self-test", action="store_true", help="Run built-in fixture check.")
    args = parser.parse_args()
    if args.self_test:
        return _self_test()
    if not args.path:
        parser.error("path is required unless --self-test")
    path = args.path.resolve()
    if path.is_dir():
        export = path / "udp_ipbox_export.txt"
        pcap = path / "capture.pcapng"
        if export.is_file():
            rows = _rows_from_export(export)
        elif pcap.is_file() and tshark_rows:
            rows = _rows_from_pcap(pcap, rest_ip=args.rest_ip)
        else:
            print(f"Need {export} or {pcap}", file=sys.stderr)
            return 1
    elif path.is_file() and path.suffix in (".txt",):
        rows = _rows_from_export(path)
    else:
        print(f"Unsupported path: {path}", file=sys.stderr)
        return 1

    data = analyze(rows, hub_ip=args.hub_ip, relay_ip=args.relay_ip)
    _emit_report(data)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
