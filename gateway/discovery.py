"""Standalone field module discovery for the IPBuilding gateway.

Discovery paths
---------------
1. **HTTP sweep** (always available, primary)
   Concurrently probe ``GET http://10.10.1.{x}/api.html?method=getSysSet``
   over a configurable IP range.  Identifies module type and firmware from
   the response.

2. **UDP/10001 probe** (secondary — requires RE spike confirmation)
   Broadcast ``01 00 00 00`` and collect replies.  Only reliable when the
   host is running as hub ``10.10.1.1``.  Enable with ``--udp-probe``.

ID model
--------
- No ``ipbox_id`` in output — IPBox component IDs are not available from
  module HTTP or UDP.  Use ``scripts/discover_from_ipbox.py`` to obtain them.
- ``entity_id`` is never stored; always derived on-the-fly as
  ``"{ip}:{device_type}:{channel}"`` via :func:`gateway.installation.make_entity_id`.

CLI
---
    python -m gateway.discover [--output devices.json.discovered]
                               [--range-start 30] [--range-end 59]
                               [--subnet 10.10.1]
                               [--udp-probe] [--udp-duration 30]

After the spike (Task 2), update ``_DEVTYPE_MAP`` if ``getSysSet`` devtype
codes differ from the current hypotheses.
"""
from __future__ import annotations

import asyncio
import socket
from dataclasses import dataclass
from typing import Any

import aiohttp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE_IP_RANGE = range(30, 60)  # 10.10.1.30 – 10.10.1.59

# devtype codes from api.html?method=getSysSet
# Values confirmed via RE of embedded HTTP (IPBUILDING_KNOWLEDGE.md §2A/B/C)
# Update after Task 2 spike if getSysSet values differ.
_DEVTYPE_MAP: dict[str, str] = {
    "1": "relay",   # IP200PoE / IP0200PoE
    "2": "dimmer",  # IP0300PoE (to verify via RE spike)
    "4": "input",   # IP1100PoE (to verify via RE spike)
}

UDP_PROBE_PAYLOAD = b"\x01\x00\x00\x00"
UDP_LISTEN_PORT = 10001


# ---------------------------------------------------------------------------
# Data model
# ---------------------------------------------------------------------------

@dataclass
class DiscoveredModule:
    """A field module discovered via HTTP or UDP probe."""

    ip: str
    device_type: str  # "relay" | "dimmer" | "input" | "unknown_{code}"
    firmware: str = ""
    mac: str = ""


# ---------------------------------------------------------------------------
# UDP/10001 (secondary path — confirm via RE spike before relying on this)
# ---------------------------------------------------------------------------

def parse_udp10001_reply(src_ip: str, payload: bytes) -> DiscoveredModule | None:
    """Parse a UDP/10001 reply payload from a field module.

    The exact reply format is not confirmed by RE yet (Task 2 spike pending).
    Current behaviour: any non-probe payload of ≥ 2 bytes is treated as a
    presence signal.  Update this function after Task 2 evidence.

    Returns ``None`` for:
    - Payloads that are ≤ 1 byte (too short)
    - The own probe echoed back (``01 00 00 00``)
    """
    if len(payload) < 2:
        return None
    if payload == UDP_PROBE_PAYLOAD:
        return None
    return DiscoveredModule(ip=src_ip, device_type="unknown")


async def probe_udp10001(
    duration: float = 30.0,
    send_probe: bool = True,
) -> list[DiscoveredModule]:
    """Send UDP/10001 broadcast and collect module replies.

    Requires the host to be bound as hub ``10.10.1.1`` for reliable replies.
    Enable with ``--udp-probe`` in the CLI.
    """
    results: dict[str, DiscoveredModule] = {}
    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEPORT, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", UDP_LISTEN_PORT))
        sock.setblocking(False)
    except OSError:
        return []

    loop = asyncio.get_running_loop()
    if send_probe:
        for target in ["255.255.255.255", "233.89.188.1"]:
            sock.sendto(UDP_PROBE_PAYLOAD, (target, UDP_LISTEN_PORT))

    start = loop.time()
    while loop.time() - start < duration:
        try:
            data, addr = await loop.run_in_executor(None, lambda: sock.recvfrom(256))
            mod = parse_udp10001_reply(addr[0], data)
            if mod and mod.ip not in results:
                results[mod.ip] = mod
        except BlockingIOError:
            await asyncio.sleep(0.05)

    sock.close()
    return list(results.values())


# ---------------------------------------------------------------------------
# HTTP sweep (primary path)
# ---------------------------------------------------------------------------

async def http_identify_module(
    ip: str,
    timeout: float = 2.0,
) -> DiscoveredModule | None:
    """GET ``api.html?method=getSysSet`` and return a ``DiscoveredModule`` or ``None``.

    The response is plain-text key=value pairs (one per line, CRLF or LF).
    """
    url = f"http://{ip}/api.html?method=getSysSet"
    try:
        async with aiohttp.ClientSession() as sess:
            async with sess.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
                if resp.status != 200:
                    return None
                text = await resp.text()

        dev_type = "unknown"
        firmware = ""
        for line in text.splitlines():
            if "=" not in line:
                continue
            k, _, v = line.partition("=")
            k, v = k.strip(), v.strip()
            if k == "devtype":
                dev_type = _DEVTYPE_MAP.get(v, f"unknown_{v}")
            elif k == "firm":
                firmware = v

        return DiscoveredModule(ip=ip, device_type=dev_type, firmware=firmware)

    except Exception:
        return None


async def sweep_http_range(
    subnet: str = "10.10.1",
    ip_range: range = MODULE_IP_RANGE,
) -> list[DiscoveredModule]:
    """Concurrently HTTP-probe all IPs in range; return responding modules."""
    tasks = [http_identify_module(f"{subnet}.{i}") for i in ip_range]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Output builder
# ---------------------------------------------------------------------------

def build_devices_json_draft(modules: list[DiscoveredModule]) -> dict[str, Any]:
    """Assemble a ``devices.json`` draft from discovered modules.

    Channels are empty — the open gateway does not require IPBox component IDs.
    ``entity_id`` is never stored; always derived on-the-fly as
    ``"{ip}:{device_type}:{channel}"`` via
    :func:`gateway.installation.make_entity_id`.

    For legacy ``ipbox_id`` (REST shim compatibility), use
    ``scripts/discover_from_ipbox.py`` instead.
    """
    return {
        "modules": [
            {
                "name": f"{m.device_type}_module",
                "ip": m.ip,
                "type": m.device_type,
                "firmware": m.firmware,
                "mac": m.mac,
                "channels": [],
            }
            for m in modules
        ]
    }
