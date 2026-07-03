"""Migrate-script: generate devices.json draft from IPBox WebConfig.

Designed for owners of a (legacy) IPBox or other central unit whose WebConfig
already knows the field modules. Triggers the WebConfig scan and reads
per-module channel info via the Import* endpoints (Step2/ImportRelayInfo,
Step2/ImportDimInfo, ImportInputInfo), producing ``devices.json`` with
``ipbox_id`` per channel (used by rest_shim.py during the HA-IPBuilding
transition only).

Why not just use ``ScanForModules`` response
--------------------------------------------
The WebConfig ``POST /general/Wizards/Modules/ScanForModules`` is a trigger,
not a discovery endpoint: on current firmware (WebConfig v1.8.4.3 / ASP.NET
MVC 4.0) it returns ``[]`` immediately and pushes module data to the browser
asynchronously via the SignalR ``loadingHub`` stream. To make this script
work over plain HTTP we therefore (1) POST ``ScanForModules`` to wake the
project-DB and (2) probe per-IP ``Import*`` endpoints which read the
already-populated project database. If the project-DB is empty (e.g. fresh
IPBox, never provisioned) the script fails loud with a clear instruction.

Usage
-----
    IPBOX_WEB_HOST=http://192.168.0.185 \\
    IPBOX_SESSION_COOKIE="ASP.NET_SessionId=abc123" \\
    DISCOVERY_OUTPUT=devices.discovered.json \\
    IPBOX_DISCOVERY_RANGE=30-59 \\
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

Exit codes
-----------
0  success
1  missing IPBOX_SESSION_COOKIE
2  no modules found — project-DB likely empty (see message)
"""
from __future__ import annotations

import asyncio
import json
import os
import sys
from pathlib import Path
from typing import Any

import aiohttp

BASE_URL = os.getenv("IPBOX_WEB_HOST", "http://192.168.0.185")
SESSION_COOKIE = os.getenv("IPBOX_SESSION_COOKIE", "")
OUTPUT_PATH = os.getenv("DISCOVERY_OUTPUT", "devices.discovered.json")

# Configureerbaar bereik voor de per-IP Import*-probes.
# Default = 10.10.1.30..10.10.1.59, het typische veldbus-segment.
_RANGE_ENV = os.getenv("IPBOX_DISCOVERY_RANGE", "30-59")


def _parse_range_spec(value: str) -> tuple[int, int]:
    """Parseer ``IPBOX_DISCOVERY_RANGE`` als ``"<start>-<end>"`` of ``"<n>"``.

    Geeft een duidelijke foutmelding via ``SystemExit`` als de waarde ongeldig
    is, in plaats van een onvriendelijke ``ValueError: not enough values to
    unpack`` of ``invalid literal for int()`` op module-import.
    """
    raw = value.strip()
    if not raw:
        sys.exit(
            "ERROR: IPBOX_DISCOVERY_RANGE is leeg. "
            "Verwacht formaat: '<start>-<end>' (bv. '30-59')."
        )
    parts = raw.split("-")
    if len(parts) == 1:
        try:
            n = int(parts[0])
        except ValueError:
            sys.exit(
                f"ERROR: IPBOX_DISCOVERY_RANGE={value!r} is geen geldige "
                "gehele getal. Verwacht formaat: '<start>-<end>' (bv. '30-59')."
            )
        return n, n
    if len(parts) != 2:
        sys.exit(
            f"ERROR: IPBOX_DISCOVERY_RANGE={value!r} heeft te veel '-'-tekens. "
            "Verwacht formaat: '<start>-<end>' (bv. '30-59')."
        )
    start_raw, end_raw = parts
    try:
        start = int(start_raw)
        end = int(end_raw)
    except ValueError:
        sys.exit(
            f"ERROR: IPBOX_DISCOVERY_RANGE={value!r} bevat niet-numerieke "
            "waarden. Verwacht formaat: '<start>-<end>' (bv. '30-59')."
        )
    if end < start:
        sys.exit(
            f"ERROR: IPBOX_DISCOVERY_RANGE={value!r}: end ({end}) is kleiner "
            f"dan start ({start}). Verwacht formaat: '<start>-<end>' met "
            "end >= start."
        )
    return start, end


_range_start, _range_end = _parse_range_spec(_RANGE_ENV)
DEFAULT_IP_SUFFIXES: range = range(_range_start, _range_end + 1)
IPBOX_SUBNET = "10.10.1"


async def scan_modules(base: str, cookie: str) -> list[dict[str, Any]]:
    """POST ScanForModules → list of ``{IP, Mac, IsNew, Type, Version}``.

    Response is empty (``[]``) on recent firmware; see module docstring.
    We keep the call for compatibility with older IPBox installs where the
    response is populated, and to "wake" the project-DB scan on newer ones.
    """
    headers = {"Cookie": cookie} if cookie else {}
    async with aiohttp.ClientSession(headers=headers) as sess:
        async with sess.post(f"{base}/general/Wizards/Modules/ScanForModules") as resp:
            resp.raise_for_status()
            return await resp.json(content_type=None)


async def build_devices_json(
    discovered: list[dict[str, Any]],
) -> dict[str, Any]:
    """Assemble devices.json structure from per-IP probe results.

    Each entry in ``discovered`` has the shape produced by
    :func:`probe_module`: ``{"ip", "type", "channels", "mac", "firmware"}``.

    IPBox component IDs are stored as ``ipbox_id`` (not ``id``).
    The ``id`` field does not exist in the open gateway schema.
    """
    result_modules = []
    for entry in discovered:
        ip = entry["ip"]
        dev_type = entry["type"]
        channels_raw = entry.get("channels", [])
        channels: list[dict[str, Any]] = []
        for ch in channels_raw:
            if dev_type == "input":
                # Input channels have no ipbox_id via Import* (no Import*-style
                # payload in the RE plan); we record a bare channel.
                channels.append({
                    "ch": ch.get("CH", ch.get("ch", 0)),
                })
            else:
                channels.append({
                    "ch": ch["CH"],
                    "ipbox_id": int(ch["id"]),   # IPBox ID — shim only
                    "description": ch.get("Description", ""),
                    "group": ch.get("Group", ""),
                })

        result_modules.append({
            "name": f"{dev_type}_module",
            "ip": ip,
            "type": dev_type,
            "mac": entry.get("mac", ""),
            "firmware": entry.get("firmware", ""),
            "channels": channels,
        })
    return {"modules": result_modules}


async def _probe_one_type(
    base: str,
    cookie: str,
    ip: str,
    endpoint: str,
) -> list[dict[str, Any]] | None:
    """POST an Import* endpoint; return parsed JSON list or None on 404/empty."""
    headers = {"Cookie": cookie} if cookie else {}
    async with aiohttp.ClientSession(headers=headers) as sess:
        async with sess.post(f"{base}{endpoint}", data={"ip": ip}) as resp:
            if resp.status == 404:
                return None
            resp.raise_for_status()
            data = await resp.json(content_type=None)
    if not isinstance(data, list) or not data:
        return None
    return data


async def probe_module(
    base: str, cookie: str, ip: str
) -> dict[str, Any] | None:
    """Probe a single IP for a known module by trying the Import* endpoints.

    Returns a dict ``{"ip", "type", "channels", "mac", "firmware"}`` if any of
    the three endpoints returns a non-empty list/array, else ``None``.

    The probe order matches RE_WIZARDS_PLAN.md:

    - ``POST /general/Hardware/Relais/ImportRelayInfo``  → relay (24 kanalen)
    - ``POST /general/Hardware/Dim/ImportDimInfo``       → dimmer (8 kanalen)
    - ``POST /general/Hardware/Input/ImportInputInfo``   → input (schema onbekend)
    """
    for dev_type, endpoint in (
        ("relay", "/general/Hardware/Relais/ImportRelayInfo"),
        ("dimmer", "/general/Hardware/Dim/ImportDimInfo"),
        ("input", "/general/Hardware/Input/ImportInputInfo"),
    ):
        data = await _probe_one_type(base, cookie, ip, endpoint)
        if data is not None:
            return {
                "ip": ip,
                "type": dev_type,
                "channels": data,
                "mac": "",
                "firmware": "",
            }
    return None


async def run() -> None:
    if not SESSION_COOKIE:
        print("ERROR: IPBOX_SESSION_COOKIE is not set.", file=sys.stderr)
        print("Log in via browser and copy the ASP.NET_SessionId cookie value.", file=sys.stderr)
        sys.exit(1)

    # Stap 1 — trigger de IPBox WebConfig scan. Response is leeg op recente
    # firmware, maar we houden de POST voor compatibiliteit met oudere
    # installaties waar de response wél modules bevat.
    print(f"Triggering scan on {BASE_URL}...")
    try:
        await scan_modules(BASE_URL, SESSION_COOKIE)
    except Exception as exc:
        print(f"WARN: ScanForModules mislukte ({exc}); ga door met Import*-probes.",
              file=sys.stderr)

    # Stap 2 — probe elk IP in het configureerbare veldbus-bereik.
    # We accepteren Import* op ieder IP waar het iets oplevert.
    candidates: list[str] = [f"{IPBOX_SUBNET}.{s}" for s in DEFAULT_IP_SUFFIXES]
    print(f"Probing {len(candidates)} IP(s) in {IPBOX_SUBNET}.{_range_start}–"
          f"{IPBOX_SUBNET}.{_range_end} via Import* endpoints...")

    probes = await asyncio.gather(
        *(probe_module(BASE_URL, SESSION_COOKIE, ip) for ip in candidates)
    )
    discovered = [p for p in probes if p is not None]

    if not discovered:
        print(
            "ERROR: Geen modules gevonden via Import*-endpoints.\n"
            "  Mogelijk is de IPBox-project-DB leeg (verse doos of nooit\n"
            "  geprovisioneerd). Open in een browser:\n"
            f"    {BASE_URL}/general/Wizards/Modules/Index\n"
            "  klik 'Start scan', wijs minimaal één module toe, en draai\n"
            "  dit script opnieuw.\n"
            "  Voor een installatie zonder IPBox gebruik je `gateway.discover`.",
            file=sys.stderr,
        )
        sys.exit(2)

    print(f"Found {len(discovered)} module(s):")
    for d in discovered:
        chans = len(d["channels"])
        print(f"  - {d['ip']:>15s}  {d['type']:<7s}  ({chans} channels)")

    output = await build_devices_json(discovered)

    apply_url = os.getenv("GATEWAY_APPLY_URL", "")
    if len(sys.argv) > 1 and "--apply" in sys.argv:
        import argparse
        p = argparse.ArgumentParser(add_help=False)
        p.add_argument("--apply", metavar="GATEWAY_URL")
        p.add_argument("--mode", default="merge_modules")
        p.add_argument("--dry-run", action="store_true")
        args, _ = p.parse_known_args()
        apply_url = args.apply or apply_url
        if apply_url:
            import subprocess
            with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
                json.dump(output, fh, indent=2, ensure_ascii=False)
            cmd = [
                sys.executable,
                str(Path(__file__).resolve().parent / "apply_installation.py"),
                "--gateway", apply_url,
                "--mode", args.mode,
                "--file", OUTPUT_PATH,
            ]
            if args.dry_run:
                cmd.append("--dry-run")
            sys.exit(subprocess.run(cmd).returncode)

    with open(OUTPUT_PATH, "w", encoding="utf-8") as fh:
        json.dump(output, fh, indent=2, ensure_ascii=False)
    print(f"\nWritten to: {OUTPUT_PATH}")
    print("Review and rename to devices.json when satisfied, or re-run with --apply http://GATEWAY:8080")


if __name__ == "__main__":
    asyncio.run(run())