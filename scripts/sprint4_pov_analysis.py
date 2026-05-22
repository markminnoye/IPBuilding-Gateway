#!/usr/bin/env python3
"""Sprint 4 — POV comparison analysis.

Compare three captures from different mirror POVs (7←15, 7←14, 7←12)
and produce a summary table of bidirectionality per device.

Usage:
    python3 scripts/sprint4_pov_analysis.py captures/sprint4_pov_comparison_YYYYMMDDTHHMMSS/
"""

from __future__ import annotations

import json
import subprocess
import sys
from collections import defaultdict
from pathlib import Path


def run_wireshark_stats_endpoints(pcap_path: Path, label: str) -> dict:
    """Get wireshark endpoints stats for a pcap."""
    result = subprocess.run(
        [
            "tshark",
            "-r", str(pcap_path),
            "-z", "endpoints,ipv4",
            "-q", "-n",
        ],
        capture_output=True,
        text=True,
    )
    endpoints = {}
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        parts = line.split()
        if len(parts) >= 6 and parts[0][0].isdigit():
            # tshark endpoints format: IP  Tx frames  Tx bytes  Rx frames  Rx bytes ...
            try:
                ip = parts[0]
                rx_frames = int(parts[4])
                tx_frames = int(parts[2])
                endpoints[ip] = {"tx": tx_frames, "rx": rx_frames}
            except (ValueError, IndexError):
                pass
    return endpoints


def summarize_pov(pcap_path: Path, pov_label: str) -> dict:
    """Summarize bidirectionality for a single POV capture."""
    endpoints = run_wireshark_stats_endpoints(pcap_path, pov_label)

    devices = {
        "10.10.1.30": "relay",
        "10.10.1.40": "dimmer",
        "10.10.1.50": "input",
    }

    result = {"pov": pov_label, "devices": {}}
    for ip, name in devices.items():
        ep = endpoints.get(ip, {"tx": 0, "rx": 0})
        result["devices"][name] = {"tx": ep["tx"], "rx": ep["rx"], "bidirectional": ep["rx"] > 0}
    return result


def main() -> int:
    if len(sys.argv) < 2:
        print("Usage: sprint4_pov_analysis.py <sprint4_session_dir>")
        return 1

    session_dir = Path(sys.argv[1])
    if not session_dir.is_dir():
        print(f"Not a directory: {session_dir}")
        return 1

    povs = sorted(session_dir.glob("pov_*/capture.pcapng"))
    if len(povs) < 3:
        print(f"Expected 3 POV captures, found {len(povs)}")
        return 1

    results = []
    for pcap_path in povs:
        pov_dir = pcap_path.parent
        pov_label = pov_dir.name  # e.g. "pov_1_sprint4_pov_a"
        print(f"Analyzing: {pov_label} ...", end=" ", flush=True)
        try:
            summary = summarize_pov(pcap_path, pov_label)
            results.append(summary)
            print("done")
        except Exception as e:
            print(f"ERROR: {e}")

    # Print comparison table
    print("\n" + "=" * 70)
    print("SPRINT 4 — POV VERGELIJKING")
    print("=" * 70)
    print(f"{'POV':<30} {'Relay Rx':>10} {'Dimmer Rx':>10} {'Input Rx':>10}")
    print("-" * 70)
    for r in results:
        relay_rx = r["devices"]["relay"]["rx"]
        dimmer_rx = r["devices"]["dimmer"]["rx"]
        input_rx = r["devices"]["input"]["rx"]
        print(f"{r['pov']:<30} {relay_rx:>10} {dimmer_rx:>10} {input_rx:>10}")

    print("-" * 70)
    print("\nBidirectionality (Rx > 0):")
    print(f"{'POV':<30} {'Relay':>8} {'Dimmer':>8} {'Input':>8}")
    for r in results:
        relay_bi = "YES" if r["devices"]["relay"]["bidirectional"] else "no"
        dimmer_bi = "YES" if r["devices"]["dimmer"]["bidirectional"] else "no"
        input_bi = "YES" if r["devices"]["input"]["bidirectional"] else "no"
        print(f"{r['pov']:<30} {relay_bi:>8} {dimmer_bi:>8} {input_bi:>8}")

    print("\n" + "=" * 70)
    print("CONCLUSIE:")
    # Which POVs capture which device replies
    relay_povs = [r["pov"] for r in results if r["devices"]["relay"]["bidirectional"]]
    dimmer_povs = [r["pov"] for r in results if r["devices"]["dimmer"]["bidirectional"]]
    input_povs = [r["pov"] for r in results if r["devices"]["input"]["bidirectional"]]

    print(f"  Relay→hub reply zichtbaar op: {relay_povs or 'GEEN'}")
    print(f"  Dimmer→hub reply zichtbaar op: {dimmer_povs or 'GEEN'}")
    print(f"  Input→hub reply zichtbaar op: {input_povs or 'GEEN'}")

    if relay_povs:
        print(f"\n  Aanbevolen standaard-POV voor relay: {relay_povs[0]}")
    if dimmer_povs:
        print(f"  Aanbevolen standaard-POV voor dimmer: {dimmer_povs[0]}")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())