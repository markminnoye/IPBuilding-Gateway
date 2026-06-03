"""Migrate-script: generate devices.json draft from IPBox WebConfig.

Calls the IPBox WebConfig wizard endpoints to discover all field modules and
their channels (including IPBox component IDs stored as ``ipbox_id``).

Usage
-----
    IPBOX_WEB_HOST=http://192.168.0.185 \\
    IPBOX_SESSION_COOKIE="ASP.NET_SessionId=abc123" \\
    DISCOVERY_OUTPUT=devices.discovered.json \\
    python scripts/discover_from_ipbox.py

Auth
----
Log in to the IPBox WebConfig in a browser, open DevTools → Application →
Cookies, copy the value of ``ASP.NET_SessionId`` and pass it via the env var.

Output
------
devices.discovered.json — same schema as devices.json, with ``ipbox_id``
per channel (the IPBox component ID, used exclusively by rest_shim.py during
the HA-IPBuilding transition). This file can overwrite devices.json after
review (scratch test — no merge with previous config).
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from typing import Any

import aiohttp

BASE_URL = os.getenv("IPBOX_WEB_HOST", "http://192.168.0.185")
SESSION_COOKIE = os.getenv("IPBOX_SESSION_COOKIE", "")
OUTPUT_PATH = os.getenv("DISCOVERY_OUTPUT", "devices.discovered.json")

TYPE_MAP: dict[str, str] = {
    "Relais": "relay",
    "Dim": "dimmer",
    "Input": "input",
}


def mac_decimal_to_hex(mac_decimal: str) -> str:
    """Convert IPBox MAC notation ``'0.36.119.82.172.190'`` to ``'00:24:77:52:ac:be'``."""
    parts = mac_decimal.split(".")
    return ":".join(f"{int(p):02x}" for p in parts)


async def scan_modules(base: str, cookie: str) -> list[dict[str, Any]]:
    """POST ScanForModules → list of ``{IP, Mac, IsNew, Type, Version}``."""
    headers = {"Cookie": cookie} if cookie else {}
    async with aiohttp.ClientSession(headers=headers) as sess:
        async with sess.post(f"{base}/general/Wizards/Modules/ScanForModules") as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def import_relay_channels(
    base: str, cookie: str, ip: str
) -> list[dict[str, Any]]:
    """POST ImportRelayInfo → list of ``{id, CH, Description, Group, ...}``."""
    headers = {"Cookie": cookie} if cookie else {}
    async with aiohttp.ClientSession(headers=headers) as sess:
        async with sess.post(
            f"{base}/general/Hardware/Relais/ImportRelayInfo",
            data={"ip": ip},
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def import_dimmer_channels(
    base: str, cookie: str, ip: str
) -> list[dict[str, Any]]:
    """POST ImportDimInfo → list of ``{id, CH, Description, Group, DimMax, DimMin}``."""
    headers = {"Cookie": cookie} if cookie else {}
    async with aiohttp.ClientSession(headers=headers) as sess:
        async with sess.post(
            f"{base}/general/Hardware/Dim/ImportDimInfo",
            data={"ip": ip},
        ) as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def build_devices_json(
    modules: list[dict[str, Any]],
    relay_channels: dict[str, list[dict[str, Any]]],
    dimmer_channels: dict[str, list[dict[str, Any]]],
) -> dict[str, Any]:
    """Assemble devices.json structure from scan + import results.

    IPBox component IDs are stored as ``ipbox_id`` (not ``id``).
    The ``id`` field does not exist in the open gateway schema.
    """
    result_modules = []
    for mod in modules:
        ip = mod["IP"]
        raw_type = mod.get("Type", "")
        dev_type = TYPE_MAP.get(raw_type, raw_type.lower())
        channels: list[dict[str, Any]] = []

        if dev_type == "relay":
            for ch in relay_channels.get(ip, []):
                channels.append({
                    "ch": ch["CH"],
                    "ipbox_id": int(ch["id"]),   # IPBox ID — shim only
                    "description": ch.get("Description", ""),
                    "group": ch.get("Group", ""),
                })
        elif dev_type == "dimmer":
            for ch in dimmer_channels.get(ip, []):
                channels.append({
                    "ch": ch["CH"],
                    "ipbox_id": int(ch["id"]),   # IPBox ID — shim only
                    "description": ch.get("Description", ""),
                    "group": ch.get("Group", ""),
                })
        # input: geen kanalen via ImportInfo

        result_modules.append({
            "name": f"{dev_type}_module",
            "ip": ip,
            "type": dev_type,
            "mac": mac_decimal_to_hex(mod.get("Mac", "")),
            "firmware": mod.get("Version", ""),
            "channels": channels,
        })
    return {"modules": result_modules}


async def run() -> None:
    if not SESSION_COOKIE:
        print("ERROR: IPBOX_SESSION_COOKIE is not set.", file=sys.stderr)
        print("Log in via browser and copy the ASP.NET_SessionId cookie value.", file=sys.stderr)
        sys.exit(1)

    print(f"Scanning modules on {BASE_URL}...")
    modules = await scan_modules(BASE_URL, SESSION_COOKIE)
    print(f"Found {len(modules)} module(s): {[m['IP'] for m in modules]}")

    relay_channels: dict[str, list] = {}
    dimmer_channels: dict[str, list] = {}

    for mod in modules:
        ip = mod["IP"]
        raw_type = mod.get("Type", "")
        if raw_type == "Relais":
            print(f"  Importing relay channels for {ip}...")
            relay_channels[ip] = await import_relay_channels(BASE_URL, SESSION_COOKIE, ip)
            print(f"    → {len(relay_channels[ip])} channels")
        elif raw_type == "Dim":
            print(f"  Importing dimmer channels for {ip}...")
            dimmer_channels[ip] = await import_dimmer_channels(BASE_URL, SESSION_COOKIE, ip)
            print(f"    → {len(dimmer_channels[ip])} channels")
        else:
            print(f"  Input module {ip}: no channel import needed")

    output = await build_devices_json(modules, relay_channels, dimmer_channels)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWritten to: {OUTPUT_PATH}")
    print("Review and rename to devices.json when satisfied.")


if __name__ == "__main__":
    asyncio.run(run())
