#!/usr/bin/env python3
"""Count UDP/1001 frames per direction on a raw pcap (Fase 1 debugplan en7).

Examples:
  python3 scripts/udp1001_bidir_counts.py captures/2026-05-14T214007Z_push-pull-run-a-quiet-evening/capture.pcapng
  python3 scripts/udp1001_bidir_counts.py --session captures/2026-05-14T214007Z_push-pull-run-a-quiet-evening
  python3 scripts/udp1001_bidir_counts.py --rest-ip 192.168.1.42 a.pcapng b.pcapng
"""

from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _count(pcap: Path, display_filter: str) -> int:
    cmd = ["tshark", "-r", str(pcap), "-Y", display_filter, "-T", "fields", "-e", "frame.number"]
    proc = subprocess.run(cmd, capture_output=True, text=True)
    if proc.returncode != 0:
        print(proc.stderr, file=sys.stderr)
        raise SystemExit(f"tshark failed ({proc.returncode}) for {pcap}")
    lines = [ln for ln in proc.stdout.splitlines() if ln.strip()]
    return len(lines)


def summarize_session(
    pcap: Path,
    *,
    hub: str,
    relay: str,
    dimmer: str,
    home: str,
) -> dict[str, int]:
    base = "udp.port==1001"
    return {
        "hub_to_relay": _count(pcap, f"{base} && ip.src=={hub} && ip.dst=={relay}"),
        "relay_to_hub": _count(pcap, f"{base} && ip.src=={relay} && ip.dst=={hub}"),
        "dimmer_to_home": _count(pcap, f"{base} && ip.src=={dimmer} && ip.dst=={home}"),
        "home_to_dimmer": _count(pcap, f"{base} && ip.src=={home} && ip.dst=={dimmer}"),
        "dimmer_to_hub": _count(pcap, f"{base} && ip.src=={dimmer} && ip.dst=={hub}"),
        "hub_to_dimmer": _count(pcap, f"{base} && ip.src=={hub} && ip.dst=={dimmer}"),
    }


def main() -> int:
    ap = argparse.ArgumentParser(description="UDP/1001 direction counts (raw pcap, tshark).")
    ap.add_argument(
        "paths",
        nargs="*",
        type=Path,
        help="capture.pcapng files (or omit when using --session)",
    )
    ap.add_argument(
        "--session",
        type=Path,
        default=None,
        help="Session directory containing capture.pcapng",
    )
    ap.add_argument("--hub-ip", default="10.10.1.1")
    ap.add_argument("--relay-ip", default="10.10.1.30")
    ap.add_argument("--dimmer-ip", default="10.10.1.40")
    ap.add_argument("--rest-ip", default="192.168.0.185", help="Home-LAN IPBox / REST host in capture")
    args = ap.parse_args()

    pcaps: list[Path] = []
    if args.session:
        p = (args.session / "capture.pcapng").resolve()
        if not p.is_file():
            print(f"Missing {p}", file=sys.stderr)
            return 1
        pcaps.append(p)
    for raw in args.paths:
        p = raw.resolve()
        if not p.is_file():
            print(f"Missing {p}", file=sys.stderr)
            return 1
        pcaps.append(p)
    if not pcaps:
        print("Provide at least one pcap path or --session", file=sys.stderr)
        return 1

    print("# UDP/1001 direction counts (objective; raw pcap)")
    print(f"# hub={args.hub_ip} relay={args.relay_ip} dimmer={args.dimmer_ip} home_rest={args.rest_ip}")
    print("")
    print("| pcap | hub→relay | relay→hub | dimmer→home | home→dimmer | dimmer→hub | hub→dimmer |")
    print("|------|-----------|-----------|-------------|-------------|------------|------------|")
    for pcap in pcaps:
        c = summarize_session(
            pcap,
            hub=args.hub_ip,
            relay=args.relay_ip,
            dimmer=args.dimmer_ip,
            home=args.rest_ip,
        )
        label = pcap.name if len(pcaps) == 1 else str(pcap)
        print(
            f"| {label} | {c['hub_to_relay']} | {c['relay_to_hub']} | "
            f"{c['dimmer_to_home']} | {c['home_to_dimmer']} | {c['dimmer_to_hub']} | {c['hub_to_dimmer']} |"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
