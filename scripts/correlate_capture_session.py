#!/usr/bin/env python3
"""Post-process a capture session: UDP from IPBox + optional ASCII, written next to manifest.

Usage:
  python3 scripts/correlate_capture_session.py captures/2026-05-04T104550Z_golden-protocol-capture
  python3 scripts/correlate_capture_session.py SESSION --verdict-profile relay --rest-ip 192.168.1.42

Requires: tshark in PATH, readable capture.pcapng.
"""

from __future__ import annotations

import argparse
import binascii
from collections import Counter
import json
import subprocess
import sys
from pathlib import Path

from dimmer_payload_parser import parse_dimmer_payload_ascii
from relay_payload_parser import parse_relay_payload_ascii


def payload_hex_to_ascii(h: str) -> str:
    h = h.strip()
    if not h or len(h) % 2:
        return ""
    try:
        raw = binascii.unhexlify(h)
    except binascii.Error:
        return ""
    return raw.decode("ascii", errors="replace")


def tshark_rows(pcap: Path, rest_ip: str = "192.168.0.185") -> list[tuple[str, str, str, str, str, str, str]]:
    # ip.addr: either direction; include home REST IP — some mirrors show relay -> IPBox home leg.
    udp_hosts = (
        "(ip.addr==10.10.1.1 or ip.addr==10.10.1.30 or ip.addr==10.10.1.40 or "
        f"ip.addr==10.10.1.50 or ip.addr=={rest_ip})"
    )
    cmd = [
        "tshark",
        "-r",
        str(pcap),
        "-Y",
        f"udp && {udp_hosts}",
        "-T",
        "fields",
        "-e",
        "frame.time_epoch",
        "-e",
        "frame.time_relative",
        "-e",
        "ip.src",
        "-e",
        "udp.srcport",
        "-e",
        "ip.dst",
        "-e",
        "udp.dstport",
        "-e",
        "udp.payload",
    ]
    out = subprocess.check_output(cmd, text=True, stderr=subprocess.DEVNULL)
    rows: list[tuple[str, str, str, str, str, str, str]] = []
    for line in out.splitlines():
        parts = line.split("\t")
        if len(parts) < 7:
            continue
        rows.append(
            (
                parts[0],
                parts[1],
                parts[2],
                parts[3],
                parts[4],
                parts[5],
                parts[6] if len(parts) > 6 else "",
            )
        )
    return rows


def load_rest_events(manifest: Path) -> list[dict[str, str]]:
    events: list[dict[str, str]] = []
    with manifest.open(encoding="utf-8") as f:
        for line in f:
            line = line.strip()
            if not line:
                continue
            try:
                obj = json.loads(line)
            except json.JSONDecodeError:
                continue
            if obj.get("event") == "rest_action":
                events.append(
                    {
                        "step_id": str(obj.get("step_id", "")),
                        "t_utc": str(obj.get("t_utc", "")),
                        "url": str(obj.get("url", "")),
                    }
                )
    return events


def build_dimmer_command_summary(rows: list[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """Return grouped counts for parsed dimmer command payloads."""
    counter: Counter[tuple[str, int, int]] = Counter()
    for _, _, _, _, _, _, pl in rows:
        asc = payload_hex_to_ascii(pl)
        parsed = parse_dimmer_payload_ascii(asc)
        if not parsed:
            continue
        if parsed.get("family") != "dimmer_command":
            continue
        channel = parsed.get("channel")
        value_percent = parsed.get("value_percent")
        action = parsed.get("action")
        if not isinstance(channel, int) or not isinstance(value_percent, int) or not isinstance(action, str):
            continue
        counter[(action, channel, value_percent)] += 1

    lines: list[str] = []
    lines.append("## Dimmer command summary (parsed)")
    lines.append("count\taction\tchannel\tvalue_percent")
    for (action, channel, value_percent), count in sorted(
        counter.items(), key=lambda item: (item[0][1], item[0][0], item[0][2])
    ):
        lines.append(f"{count}\t{action}\t{channel}\t{value_percent}")
    if len(lines) == 2:
        lines.append("(no parsed dimmer_command rows found)")
    return lines


def build_relay_command_summary(rows: list[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """Return grouped counts for parsed relay command payloads."""
    counter: Counter[tuple[str, int]] = Counter()
    for _, _, _, _, _, _, pl in rows:
        asc = payload_hex_to_ascii(pl)
        parsed = parse_relay_payload_ascii(asc)
        if not parsed:
            continue
        if parsed.get("family") != "relay_command":
            continue
        channel = parsed.get("channel")
        action = parsed.get("action")
        if not isinstance(channel, int) or not isinstance(action, str):
            continue
        counter[(action, channel)] += 1

    lines: list[str] = []
    lines.append("## Relay command summary (parsed)")
    lines.append("count\taction\tchannel")
    for (action, channel), count in sorted(
        counter.items(), key=lambda item: (item[0][1], item[0][0])
    ):
        lines.append(f"{count}\t{action}\t{channel}")
    if len(lines) == 2:
        lines.append("(no parsed relay_command rows found)")
    return lines


def build_relay_status_summary(rows: list[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """Return grouped counts for parsed relay status payloads."""
    counter: Counter[tuple[int, str, str]] = Counter()
    for _, _, _, _, _, _, pl in rows:
        asc = payload_hex_to_ascii(pl)
        parsed = parse_relay_payload_ascii(asc)
        if not parsed:
            continue
        if parsed.get("family") != "relay_status":
            continue
        channel = parsed.get("channel")
        state = parsed.get("state")
        state_code = parsed.get("state_code")
        if not isinstance(channel, int) or not isinstance(state, str) or not isinstance(state_code, str):
            continue
        counter[(channel, state, state_code)] += 1

    lines: list[str] = []
    lines.append("## Relay status summary (parsed)")
    lines.append("count\tchannel\tstate\tstate_code")
    for (channel, state, state_code), count in sorted(counter.items(), key=lambda item: (item[0][0], item[0][1])):
        lines.append(f"{count}\t{channel}\t{state}\t{state_code}")
    if len(lines) == 2:
        lines.append("(no parsed relay_status rows found)")
    return lines


def build_unparsed_payload_summary(rows: list[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """Return grouped counts for payloads that parser does not classify."""
    counter: Counter[tuple[str, str, str, str, str]] = Counter()
    for _, _, src, sport, dst, dport, pl in rows:
        asc = payload_hex_to_ascii(pl)
        parsed = parse_dimmer_payload_ascii(asc) or parse_relay_payload_ascii(asc)
        if parsed:
            continue
        if not asc:
            continue
        counter[(src, sport, dst, dport, asc)] += 1

    lines: list[str] = []
    lines.append("## Unparsed payload summary (by src/sport -> dst/dport, payload_ascii)")
    lines.append("count\tsrc\tsport\tdst\tdport\tpayload_ascii")
    for (src, sport, dst, dport, asc), count in sorted(
        counter.items(), key=lambda item: (item[0][0], item[0][2], -item[1], item[0][4])
    ):
        lines.append(f"{count}\t{src}\t{sport}\t{dst}\t{dport}\t{asc}")
    if len(lines) == 2:
        lines.append("(no unparsed payloads)")
    return lines


def build_direction_summary(rows: list[tuple[str, str, str, str, str, str, str]]) -> list[str]:
    """Return grouped counts by UDP source/destination and ports."""
    counter: Counter[tuple[str, str, str, str]] = Counter()
    for _, _, src, sport, dst, dport, _ in rows:
        counter[(src, sport, dst, dport)] += 1

    lines: list[str] = []
    lines.append("## UDP direction summary")
    lines.append("count\tsrc\tsport\tdst\tdport")
    for (src, sport, dst, dport), count in sorted(
        counter.items(), key=lambda item: (-item[1], item[0][0], item[0][2], item[0][1], item[0][3])
    ):
        lines.append(f"{count}\t{src}\t{sport}\t{dst}\t{dport}")
    if len(lines) == 2:
        lines.append("(no udp rows found)")
    return lines


def _bidirectional_udp(
    rows: list[tuple[str, str, str, str, str, str, str]], host_a: str, host_b: str
) -> bool:
    """True if there is at least one UDP packet A->B and one B->A (by IP src/dst)."""
    forward = False
    backward = False
    for _, _, src, _, dst, _, _ in rows:
        if src == host_a and dst == host_b:
            forward = True
        elif src == host_b and dst == host_a:
            backward = True
        if forward and backward:
            return True
    return False


def _device_sees_hub_or_home(
    rows: list[tuple[str, str, str, str, str, str, str]],
    device_ip: str,
    hub_ip: str,
    home_rest_ip: str,
) -> bool:
    return _bidirectional_udp(rows, device_ip, hub_ip) or _bidirectional_udp(
        rows, device_ip, home_rest_ip
    )


def build_status_verdict_gate(
    rows: list[tuple[str, str, str, str, str, str, str]],
    *,
    hub_ip: str,
    home_rest_ip: str,
    verdict_profile: str,
    verdict_pairs: list[tuple[str, str]],
) -> tuple[list[str], str]:
    """Return markdown lines for the gate section and a single-line verdict (PASS|WARN|SKIP)."""
    lines: list[str] = []
    lines.append("## Status verdict gate (automated)")
    lines.append(
        "Do not treat parsed relay_status / absence-of-reply claims as wire-truth when WARN; "
        "see resources_and_docs/workflows/CAPTURE_LIVE_STATUS.md directional validity gate."
    )

    if verdict_pairs:
        ok_pairs: list[str] = []
        bad_pairs: list[str] = []
        for a, b in verdict_pairs:
            if _bidirectional_udp(rows, a, b):
                ok_pairs.append(f"{a} <-> {b}")
            else:
                bad_pairs.append(f"{a} <-> {b}")
        if not bad_pairs:
            verdict = "PASS"
            lines.append(f"STATUS_VERDICT_GATE: {verdict}")
            lines.append(f"All explicit --verdict-pair checks bidirectional: {', '.join(ok_pairs)}")
        else:
            verdict = "WARN"
            lines.append(f"STATUS_VERDICT_GATE: {verdict}")
            lines.append(f"Missing return direction for: {', '.join(bad_pairs)}")
            if ok_pairs:
                lines.append(f"Bidirectional pairs satisfied: {', '.join(ok_pairs)}")
        return lines, verdict

    if verdict_profile == "none":
        lines.append("STATUS_VERDICT_GATE: SKIP (--verdict-profile none; use UDP direction summary manually)")
        return lines, "SKIP"

    profile_devices: dict[str, list[str]] = {
        "relay": ["10.10.1.30"],
        "dimmer": ["10.10.1.40"],
        "input": ["10.10.1.50"],
        "any": ["10.10.1.30", "10.10.1.40", "10.10.1.50"],
    }
    devices = profile_devices.get(verdict_profile, profile_devices["any"])

    satisfied: list[str] = []
    for dev in devices:
        if _device_sees_hub_or_home(rows, dev, hub_ip, home_rest_ip):
            satisfied.append(dev)

    if verdict_profile == "any":
        if satisfied:
            verdict = "PASS"
            lines.append(f"STATUS_VERDICT_GATE: {verdict}")
            lines.append(
                f"At least one controller has bidirectional UDP with {hub_ip} or {home_rest_ip}: "
                f"{', '.join(satisfied)}"
            )
        else:
            verdict = "WARN"
            lines.append(f"STATUS_VERDICT_GATE: {verdict}")
            lines.append(
                f"No bidirectional UDP for any of {', '.join(devices)} with {hub_ip} or {home_rest_ip}."
            )
        return lines, verdict

    # single-target profiles: relay | dimmer | input
    dev = devices[0]
    if _device_sees_hub_or_home(rows, dev, hub_ip, home_rest_ip):
        verdict = "PASS"
        lines.append(f"STATUS_VERDICT_GATE: {verdict}")
        lines.append(f"Controller {dev} has bidirectional UDP with {hub_ip} or {home_rest_ip}.")
    else:
        verdict = "WARN"
        lines.append(f"STATUS_VERDICT_GATE: {verdict}")
        lines.append(
            f"Controller {dev} lacks bidirectional UDP with {hub_ip} or {home_rest_ip} in this export."
        )
    return lines, verdict


def main() -> int:
    parser = argparse.ArgumentParser(description="Export IPBox UDP correlation for a session folder.")
    parser.add_argument("session_dir", type=Path, help="Path to captures/<timestamp>_golden-protocol-capture/")
    parser.add_argument(
        "--rest-ip",
        default="192.168.0.185",
        help="IPBox REST host on home LAN (tshark ip.addr filter + bidirectional gate with controllers).",
    )
    parser.add_argument(
        "--hub-ip",
        default="10.10.1.1",
        help="IPBox / hub on IPBuilding VLAN for bidirectional gate checks.",
    )
    parser.add_argument(
        "--verdict-profile",
        choices=("none", "relay", "dimmer", "input", "any"),
        default="any",
        help="Which controller(s) must show bidirectional UDP with --hub-ip or --rest-ip (default: any).",
    )
    parser.add_argument(
        "--verdict-pair",
        action="append",
        default=[],
        metavar="A,B",
        help="Repeatable. If set, gate requires every A<->B pair to be bidirectional (overrides --verdict-profile).",
    )
    args = parser.parse_args()
    session_dir = args.session_dir.resolve()
    pcap = session_dir / "capture.pcapng"
    manifest = session_dir / "manifest.jsonl"
    out_txt = session_dir / "udp_ipbox_export.txt"

    if not pcap.is_file():
        print(f"Missing PCAP: {pcap}", file=sys.stderr)
        return 1
    if not manifest.is_file():
        print(f"Missing manifest: {manifest}", file=sys.stderr)
        return 1

    verdict_pairs: list[tuple[str, str]] = []
    for raw in args.verdict_pair:
        parts = [p.strip() for p in raw.split(",")]
        if len(parts) != 2 or not parts[0] or not parts[1]:
            print(f"Invalid --verdict-pair (expected hostA,hostB): {raw!r}", file=sys.stderr)
            return 2
        verdict_pairs.append((parts[0], parts[1]))

    rows = tshark_rows(pcap, rest_ip=args.rest_ip)
    rest_events = load_rest_events(manifest)

    lines: list[str] = []
    lines.append(f"# Session: {session_dir.name}")
    lines.append(f"# PCAP: {pcap.name}")
    lines.append("")
    lines.append("## REST actions (from manifest)")
    for ev in rest_events:
        lines.append(f"- {ev['t_utc']}  {ev['step_id']}  {ev['url']}")
    lines.append("")
    lines.append("## UDP (epoch  t_rel_s  src  sport  dst  dport  payload_hex  payload_ascii  payload_parse)")
    for epoch, trel, src, sport, dst, dport, pl in rows:
        asc = payload_hex_to_ascii(pl)
        parsed = parse_dimmer_payload_ascii(asc) or parse_relay_payload_ascii(asc)
        parsed_text = json.dumps(parsed, ensure_ascii=False, separators=(",", ":")) if parsed else ""
        lines.append(f"{epoch}\t{trel}\t{src}\t{sport}\t{dst}\t{dport}\t{pl}\t{asc!r}\t{parsed_text}")

    lines.append("")
    lines.extend(build_direction_summary(rows))
    lines.append("")
    gate_lines, verdict = build_status_verdict_gate(
        rows,
        hub_ip=args.hub_ip,
        home_rest_ip=args.rest_ip,
        verdict_profile=args.verdict_profile,
        verdict_pairs=verdict_pairs,
    )
    lines.extend(gate_lines)
    lines.append("")
    lines.extend(build_dimmer_command_summary(rows))
    lines.append("")
    lines.extend(build_relay_command_summary(rows))
    lines.append("")
    lines.extend(build_relay_status_summary(rows))
    lines.append("")
    lines.extend(build_unparsed_payload_summary(rows))

    text = "\n".join(lines) + "\n"
    try:
        out_txt.write_text(text, encoding="utf-8")
        print(f"Wrote {out_txt}")
    except OSError as exc:
        fallback = session_dir.parent / f"{session_dir.name}_udp_ipbox_export.txt"
        fallback.write_text(text, encoding="utf-8")
        print(f"Wrote {fallback} (session dir not writable: {exc})")
    print(f"STATUS_VERDICT_GATE: {verdict}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
