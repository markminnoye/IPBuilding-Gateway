#!/usr/bin/env python3
"""ARP-assisted discovery spike — no extra packages (ping + arp -a).

Sends one ICMP ping per IP in range so the host ARP cache fills, then parses
``arp -an`` and filters IPBuilding field modules (OUI ``00:24:77``).

Optionally verifies each candidate with module HTTP ``getSysSet``.

Usage
-----
    python scripts/arp_discover_spike.py
    python scripts/arp_discover_spike.py --range-start 1 --range-end 254
    python scripts/arp_discover_spike.py --subnet 10.10.1 --range-start 30 --range-end 59 --http-verify

Requires: same L2/L3 as the field bus (e.g. 10.10.1.x on en7).
"""
from __future__ import annotations

import argparse
import asyncio
import json
import re
import subprocess
import sys
import urllib.error
import urllib.request
from dataclasses import dataclass

FIELD_MODULE_OUI = "00:24:77"
IPBOX_HUB_OUI = "00:30:18"

# macOS arp -an: (10.10.1.30) at 0:24:77:52:ac:be on en7 ...
_ARP_LINE = re.compile(
    r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-f:]+)",
    re.IGNORECASE,
)


@dataclass
class ArpHost:
    ip: str
    mac: str
    is_field_module: bool
    is_ipbox_hub: bool


def normalize_mac(mac: str) -> str:
    """Canonical aa:bb:cc:dd:ee:ff (macOS arp uses single-digit octets)."""
    parts = mac.lower().replace("-", ":").split(":")
    return ":".join(f"{int(p, 16):02x}" for p in parts)


def is_field_module_mac(mac: str) -> bool:
    return normalize_mac(mac).startswith(f"{FIELD_MODULE_OUI}:")


def is_ipbox_hub_mac(mac: str) -> bool:
    return normalize_mac(mac).startswith(f"{IPBOX_HUB_OUI}:")


async def ping_host(ip: str, timeout_s: float) -> bool:
    """One ping; return True if host replied (best-effort)."""
    proc = await asyncio.create_subprocess_exec(
        "ping",
        "-c",
        "1",
        "-W",
        str(max(1, int(timeout_s * 1000))),  # macOS: -W timeout in ms
        ip,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return proc.returncode == 0


async def ping_sweep(
    subnet: str,
    range_start: int,
    range_end: int,
    *,
    timeout_s: float = 0.5,
    concurrency: int = 20,
) -> tuple[int, int]:
    """Ping all IPs in [range_start, range_end]; return (replied, total)."""
    sem = asyncio.Semaphore(concurrency)
    ips = [f"{subnet}.{i}" for i in range(range_start, range_end + 1)]

    async def one(ip: str) -> bool:
        async with sem:
            return await ping_host(ip, timeout_s)

    results = await asyncio.gather(*[one(ip) for ip in ips])
    replied = sum(1 for r in results if r)
    return replied, len(ips)


def read_arp_table(subnet: str) -> list[ArpHost]:
    """Parse ``arp -an`` for entries on subnet."""
    out = subprocess.check_output(["arp", "-an"], text=True, errors="replace")
    hosts: list[ArpHost] = []
    prefix = subnet + "."
    for line in out.splitlines():
        m = _ARP_LINE.search(line)
        if not m:
            continue
        ip, mac = m.group(1), m.group(2)
        if not ip.startswith(prefix):
            continue
        if mac in ("(incomplete)", "(failed)"):
            continue
        mac_n = normalize_mac(mac)
        hosts.append(
            ArpHost(
                ip=ip,
                mac=mac_n,
                is_field_module=is_field_module_mac(mac_n),
                is_ipbox_hub=is_ipbox_hub_mac(mac_n),
            )
        )
    return hosts


def _http_get_sys_set_sync(ip: str, timeout_s: float) -> dict[str, str]:
    """GET getSysSet — JSON or key=value lines (stdlib only)."""
    url = f"http://{ip}/api.html?method=getSysSet"
    try:
        with urllib.request.urlopen(url, timeout=timeout_s) as resp:
            text = resp.read().decode("utf-8", errors="replace").strip()
    except (urllib.error.URLError, TimeoutError, OSError):
        return {}
    if not text:
        return {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
            if isinstance(data, dict):
                return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass
    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


async def http_get_sys_set(ip: str, timeout_s: float = 2.0) -> dict[str, str]:
    loop = asyncio.get_running_loop()
    return await loop.run_in_executor(
        None, lambda: _http_get_sys_set_sync(ip, timeout_s)
    )


async def main_async(args: argparse.Namespace) -> int:
    print(
        f"Ping sweep {args.subnet}.{args.range_start} – "
        f"{args.subnet}.{args.range_end} (timeout {args.ping_timeout}s, "
        f"concurrency {args.concurrency})..."
    )
    replied, total = await ping_sweep(
        args.subnet,
        args.range_start,
        args.range_end,
        timeout_s=args.ping_timeout,
        concurrency=args.concurrency,
    )
    print(f"  Ping: {replied}/{total} host(s) replied (ICMP may be ignored by some modules)")

    print("Reading ARP cache (arp -an)...")
    all_hosts = read_arp_table(args.subnet)
    field = [h for h in all_hosts if h.is_field_module]
    hub = [h for h in all_hosts if h.is_ipbox_hub]
    other = [h for h in all_hosts if not h.is_field_module and not h.is_ipbox_hub]

    print(f"  ARP on {args.subnet}.*: {len(all_hosts)} entry(ies)")
    print(f"    field modules (OUI {FIELD_MODULE_OUI}): {len(field)}")
    print(f"    IPBox hub     (OUI {IPBOX_HUB_OUI}): {len(hub)}")
    print(f"    other: {len(other)}")

    if field:
        print("\nField modules (ARP):")
        for h in sorted(field, key=lambda x: x.ip):
            print(f"  {h.ip}  {h.mac}")
    else:
        print("\nNo field-module MACs in ARP cache.")
        print("  Check: on 10.10.1.x? Try longer range or --ping-timeout 1")

    if hub:
        print("\nHub (exclude from module list):")
        for h in sorted(hub, key=lambda x: x.ip):
            print(f"  {h.ip}  {h.mac}")

    if other and args.verbose:
        print("\nOther ARP entries:")
        for h in sorted(other, key=lambda x: x.ip):
            print(f"  {h.ip}  {h.mac}")

    if args.http_verify and field:
        print("\nHTTP verify (getSysSet):")
        for h in sorted(field, key=lambda x: x.ip):
            kv = await http_get_sys_set(h.ip)
            dev = kv.get("devtype", "?")
            firm = kv.get("firm", "?")
            ok = "OK" if kv else "FAIL"
            print(f"  {h.ip}  [{ok}]  devtype={dev}  firm={firm}")

    # Compare with known reference install
    expected = {"10.10.1.30", "10.10.1.40", "10.10.1.50"}
    found_ips = {h.ip for h in field}
    if expected & found_ips:
        missing = expected - found_ips
        if missing:
            print(f"\nReference IPs missing from ARP field list: {sorted(missing)}")
        else:
            print("\nReference install: .30 .40 .50 all seen in ARP (field OUI).")

    return 0 if field or not args.require_field else 1


def main() -> None:
    parser = argparse.ArgumentParser(description="ARP discovery spike (ping + arp -a)")
    parser.add_argument("--subnet", default="10.10.1")
    parser.add_argument("--range-start", type=int, default=30)
    parser.add_argument("--range-end", type=int, default=59)
    parser.add_argument("--ping-timeout", type=float, default=0.5)
    parser.add_argument("--concurrency", type=int, default=20)
    parser.add_argument("--http-verify", action="store_true", help="curl getSysSet per field MAC")
    parser.add_argument("--verbose", action="store_true", help="Show non-field ARP entries")
    parser.add_argument(
        "--require-field",
        action="store_true",
        help="Exit 1 if no 00:24:77 entries (for CI)",
    )
    args = parser.parse_args()
    if args.range_end < args.range_start:
        print("error: range-end < range-start", file=sys.stderr)
        sys.exit(2)
    sys.exit(asyncio.run(main_async(args)))


if __name__ == "__main__":
    main()
