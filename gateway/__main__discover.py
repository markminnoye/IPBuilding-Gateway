"""CLI entrypoint: ``python -m gateway.discover``

Discovers IPBuilding field modules via HTTP sweep (primary) and optionally
UDP/10001 probe (secondary — confirm GO-A verdict in spike evidence first).

Usage
-----
    python -m gateway.discover
    python -m gateway.discover --output /tmp/found.json
    python -m gateway.discover --range-start 30 --range-end 59 --subnet 10.10.1
    python -m gateway.discover --udp-probe --udp-duration 30

Output
------
devices.json.discovered — same schema as devices.json, without ipbox_id.
Review, then merge channel/ipbox_id data from discover_from_ipbox.py if needed.
"""
import argparse
import asyncio
import json
import sys

from gateway.discovery import build_devices_json_draft, probe_udp10001, sweep_http_range


async def run(args: argparse.Namespace) -> None:
    modules_by_ip: dict[str, object] = {}

    # Primary: HTTP sweep
    print(f"HTTP sweep {args.subnet}.{args.range_start} – {args.subnet}.{args.range_end}...")
    http_modules = await sweep_http_range(
        subnet=args.subnet,
        ip_range=range(args.range_start, args.range_end + 1),
    )
    for m in http_modules:
        modules_by_ip[m.ip] = m
    print(f"  HTTP: found {len(http_modules)} module(s)")

    # Secondary: UDP/10001 (opt-in — requires GO-A verdict from spike)
    if args.udp_probe:
        print(f"UDP/10001 probe (duration {args.udp_duration}s)...")
        udp_modules = await probe_udp10001(duration=args.udp_duration)
        added = 0
        for m in udp_modules:
            if m.ip not in modules_by_ip:
                modules_by_ip[m.ip] = m
                added += 1
        print(f"  UDP:  found {len(udp_modules)} reply(ies), {added} new")

    all_modules = list(modules_by_ip.values())
    print(f"\nTotal: {len(all_modules)} module(s) discovered:")
    for m in all_modules:
        print(f"  {m.ip}  type={m.device_type}  fw={m.firmware}")

    draft = build_devices_json_draft(all_modules)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(draft, fh, indent=2, ensure_ascii=False)

    print(f"\nDraft written to: {args.output}")
    print("NOTE: no ipbox_id in output — correct for the open gateway.")
    print("For REST-shim compatibility, run scripts/discover_from_ipbox.py (requires IPBox).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover IPBuilding field modules via HTTP sweep + optional UDP/10001 probe"
    )
    parser.add_argument("--output", default="devices.json.discovered",
                        help="Output path (default: devices.json.discovered)")
    parser.add_argument("--subnet", default="10.10.1",
                        help="Subnet prefix (default: 10.10.1)")
    parser.add_argument("--range-start", type=int, default=30,
                        help="Start of IP range (default: 30)")
    parser.add_argument("--range-end", type=int, default=59,
                        help="End of IP range inclusive (default: 59)")
    parser.add_argument("--udp-probe", action="store_true",
                        help="Also send UDP/10001 probe (requires GO-A spike verdict)")
    parser.add_argument("--udp-duration", type=int, default=30,
                        help="UDP probe listen duration in seconds (default: 30)")
    args = parser.parse_args()
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
