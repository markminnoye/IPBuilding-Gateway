"""CLI entrypoint: ``python -m gateway.discover``

Discovers IPBuilding field modules.

Default (ARP-first):
  1. Ping-sweep over the configured range (populates kernel ARP cache).
  2. Read ``arp -an`` / ``/proc/net/arp`` and filter OUI 00:24:77.
  3. HTTP getSysSet + backupConfig on each ARP candidate (parallel).
  4. Falls back to full HTTP sweep if no ARP candidates are found.

Use ``--no-arp`` to revert to HTTP-only sweep (original behaviour).

Secondary (always available): UDP/10001 probe via ``--udp-probe``.

Usage
-----
    python -m gateway.discover
    python -m gateway.discover --output /tmp/found.json
    python -m gateway.discover --subnet 10.10.1 --range-start 30 --range-end 59
    python -m gateway.discover --no-arp   # HTTP-only sweep
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

from gateway.discovery import (
    build_devices_json_draft,
    discover_modules,
    probe_udp10001,
)


async def run(args: argparse.Namespace) -> None:
    ip_range = range(args.range_start, args.range_end + 1)

    # Primary: ARP-first or HTTP-only
    if args.no_arp:
        print(f"HTTP-only sweep {args.subnet}.{args.range_start} – {args.subnet}.{args.range_end}...")
        from gateway.discovery import sweep_http_range
        primary_modules = await sweep_http_range(
            subnet=args.subnet,
            ip_range=ip_range,
            use_backup_config=not args.no_backup_config,
        )
        arp_note = "(ARP disabled)"
    else:
        print(f"ARP-first {args.subnet}.{args.range_start} – {args.subnet}.{args.range_end} "
              f"(ping {args.ping_timeout}s, concurrency {args.ping_concurrency})...")
        primary_modules = await discover_modules(
            subnet=args.subnet,
            ip_range=ip_range,
            arp_first=True,
            ping_timeout=args.ping_timeout,
            http_timeout=args.http_timeout,
            ping_concurrency=args.ping_concurrency,
            use_backup_config=not args.no_backup_config,
        )
        arp_note = ""

    modules_by_ip = {m.ip: m for m in primary_modules}
    print(f"  Found {len(primary_modules)} module(s) {arp_note}")

    # Secondary: UDP/10001 (opt-in)
    if args.udp_probe:
        print(f"UDP/10001 probe (duration {args.udp_duration}s)...")
        udp_modules = await probe_udp10001(duration=args.udp_duration)
        added = 0
        for m in udp_modules:
            if m.ip not in modules_by_ip:
                modules_by_ip[m.ip] = m
                added += 1
        print(f"  UDP: {len(udp_modules)} reply(ies), {added} new")

    all_modules = list(modules_by_ip.values())
    print(f"\nTotal: {len(all_modules)} module(s) discovered:")
    for m in all_modules:
        mac_info = f"  mac={m.mac}" if m.mac else ""
        ch_info = f"  channels={len(m.channels)}" if m.channels else ""
        print(
            f"  {m.ip}  model={m.model}  type={m.device_type}  "
            f"fw={m.firmware}{mac_info}{ch_info}"
        )

    draft = build_devices_json_draft(all_modules)
    with open(args.output, "w", encoding="utf-8") as fh:
        json.dump(draft, fh, indent=2, ensure_ascii=False)

    print(f"\nDraft written to: {args.output}")
    print("NOTE: no ipbox_id in output — correct for the open gateway.")
    print("For REST-shim compatibility, run scripts/discover_from_ipbox.py (requires IPBox).")


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Discover IPBuilding field modules (ARP-first + HTTP, or HTTP-only)"
    )
    parser.add_argument("--output", default="devices.json.discovered",
                        help="Output path (default: devices.json.discovered)")
    parser.add_argument("--subnet", default="10.10.1",
                        help="Subnet prefix (default: 10.10.1)")
    parser.add_argument("--range-start", type=int, default=30,
                        help="Start of IP range (default: 30)")
    parser.add_argument("--range-end", type=int, default=59,
                        help="End of IP range inclusive (default: 59)")
    parser.add_argument("--no-arp", action="store_true",
                        help="Skip ARP-first; use HTTP-only sweep (original behaviour)")
    parser.add_argument("--no-backup-config", action="store_true",
                        help="Skip backupConfig (only getSysSet; no refNr/channels)")
    parser.add_argument("--ping-timeout", type=float, default=0.5,
                        help="ICMP ping timeout in seconds (default: 0.5)")
    parser.add_argument("--http-timeout", type=float, default=2.0,
                        help="HTTP getSysSet timeout in seconds (default: 2.0)")
    parser.add_argument("--ping-concurrency", type=int, default=20,
                        help="Max concurrent ping processes (default: 20)")
    parser.add_argument("--udp-probe", action="store_true",
                        help="Also send UDP/10001 probe (requires GO-A spike verdict)")
    parser.add_argument("--udp-duration", type=int, default=30,
                        help="UDP probe listen duration in seconds (default: 30)")
    args = parser.parse_args()
    if args.range_end < args.range_start:
        print("error: range-end must be >= range-start", file=sys.stderr)
        sys.exit(1)
    asyncio.run(run(args))


if __name__ == "__main__":
    main()
