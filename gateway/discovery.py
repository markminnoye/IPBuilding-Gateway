"""Standalone field module discovery for the IPBuilding gateway.

Discovery paths
---------------
1. **ARP-first** (default) — ping-sweep over range → kernel ARP cache →
   parse `arp -an` / `/proc/net/arp` → filter OUI `00:24:77` (field modules) →
   exclude OUI `00:30:18` (IPBox hub) → HTTP getSysSet + backupConfig.

2. **HTTP-only** (fallback) — concurrent probe ``GET api.html?method=getSysSet``
   over configureerbare IP range.

3. **UDP/10001 probe** (secondary — requires RE spike confirmation)
   Broadcast ``01 00 00 00`` and collect replies.  Only reliable when the
   host is running as hub ``10.10.1.1``.  Enable with ``--udp-probe``.

ID model
--------
- No ``ipbox_id`` in output — IPBox component IDs are not available from
  module HTTP or UDP.  Use ``scripts/discover_from_ipbox.py`` to obtain them.
- ``entity_id`` is never stored; always derived on-the-fly as
  ``"{ip}:{channel}"`` via :func:`gateway.installation.make_entity_id`.
  The device type is NOT encoded in the entity_id — it is resolved server-side
  from the installation config.

CLI
---
    python -m gateway.discover [--output devices.discovered.json]
                               [--subnet 10.10.1]
                               [--range-start 30] [--range-end 59]
                               [--no-arp]          # force HTTP-only sweep
                               [--no-backup-config]  # skip backupConfig (type/channels)
                               [--udp-probe] [--udp-duration 30]

The ``--no-arp`` flag reverts to the original HTTP-only behaviour.
"""
from __future__ import annotations

import asyncio
import json
import platform
import re
import socket
import subprocess
import sys
from dataclasses import dataclass, field
from typing import Any

import aiohttp

# ---------------------------------------------------------------------------
# Constants
# ---------------------------------------------------------------------------

MODULE_IP_RANGE = range(30, 60)  # 10.10.1.30 – 10.10.1.59

# OUI prefixes for filtering ARP results
FIELD_MODULE_OUI = "00:24:77"   # relay / dimmer / input modules
IPBOX_HUB_OUI = "00:30:18"      # IPBox hub — exclude from discovery

# devtype codes from api.html?method=getSysSet
# Values confirmed via RE of embedded HTTP (IPBUILDING_KNOWLEDGE.md §2A/B/C)
# Update after Task 2 spike if getSysSet values differ.
_DEVTYPE_MAP: dict[str, str] = {
    "1": "relay",   # IP200PoE / IP0200PoE
    "2": "dimmer",  # IP0300PoE
    "4": "input",   # IP1100PoE
}

# Map factory product name (getSysSet "name" field) → gateway type.
# Covers live firmware JSON responses where devtype is absent.
_MODEL_TO_TYPE: dict[str, str] = {
    "IP200PoE": "relay",
    "IP0200PoE": "relay",
    "IP0300PoE": "dimmer",
    "IP1100PoE": "input",
}

UDP_PROBE_PAYLOAD = b"\x01\x00\x00\x00"
UDP_LISTEN_PORT = 10001

# ARP line patterns per platform
_ARP_DARWIN = re.compile(r"\((\d+\.\d+\.\d+\.\d+)\)\s+at\s+([0-9a-f:]+)", re.IGNORECASE)
_ARP_LINUX = re.compile(r"(\d+\.\d+\.\d+\.\d+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)\s+(\S+)", re.IGNORECASE)


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
    model: str = ""   # factory product label, e.g. IP0200PoE (getSysSet name or backup refNr)
    channels: list[dict[str, Any]] = field(default_factory=list)


@dataclass(frozen=True)
class IpChange:
    """A MAC-keyed IP address change between two discovery runs."""

    mac: str
    old_ip: str
    new_ip: str


# ---------------------------------------------------------------------------
# MAC utilities
# ---------------------------------------------------------------------------

def normalize_mac(mac: str) -> str:
    """Canonicalise a MAC address to lowercase colon-separated.

    Handles:
      - macOS ``0:24:77:52:ac:be``  (single-digit octets, no leading zeros)
      - Linux ``00:24:77:52:ac:be``
      - dash-separated variants
    """
    parts = mac.lower().replace("-", ":").split(":")
    return ":".join(f"{int(p, 16):02x}" for p in parts if p)


def is_field_module_mac(mac: str) -> bool:
    return normalize_mac(mac).startswith(f"{FIELD_MODULE_OUI}:")


def is_ipbox_hub_mac(mac: str) -> bool:
    return normalize_mac(mac).startswith(f"{IPBOX_HUB_OUI}:")


def detect_mac_ip_changes(
    modules: list[DiscoveredModule],
    baseline: "InstallationConfig | None",  # type: ignore[name-defined] # lazy to avoid circular import
) -> list[IpChange]:
    """Compare discovered module IPs against a MAC-keyed baseline config.

    Returns a list of :class:`IpChange` for every module whose MAC is known
    in the baseline but whose current IP differs from the stored IP.
    """
    if baseline is None:
        return []
    changes: list[IpChange] = []
    for mod in modules:
        if not mod.mac:
            continue
        mac = normalize_mac(mod.mac)
        existing = baseline.module_by_mac(mac)
        if existing is None:
            continue
        if existing.ip != mod.ip:
            changes.append(IpChange(mac=mac, old_ip=existing.ip, new_ip=mod.ip))
    return changes


# ---------------------------------------------------------------------------
# ARP table parsing
# ---------------------------------------------------------------------------

def parse_arp_table(subnet: str) -> list[tuple[str, str]]:
    """Read the kernel ARP table and return (ip, mac) pairs on subnet.

    Platform-aware:
      - macOS / Darwin: ``arp -an``
      - Linux: ``/proc/net/arp``

    Skips incomplete / failed entries and excludes the subnet broadcast address.
    Returns list of (ip_normalised, mac_normalised).
    """
    prefix = subnet + "."
    results: list[tuple[str, str]] = []

    try:
        if platform.system() == "Darwin":
            out = subprocess.check_output(["arp", "-an"], text=True, errors="replace")
            for line in out.splitlines():
                m = _ARP_DARWIN.search(line)
                if not m:
                    continue
                ip, mac_raw = m.group(1), m.group(2)
                if not ip.startswith(prefix):
                    continue
                if "(incomplete)" in line or "(failed)" in line:
                    continue
                results.append((ip, normalize_mac(mac_raw)))
        else:
            # Linux — /proc/net/arp
            with open("/proc/net/arp", encoding="utf-8", errors="replace") as fh:
                next(fh, None)  # skip header line
                for line in fh:
                    parts = line.split()
                    if len(parts) < 4:
                        continue
                    ip, hw_type, flag, mac_raw = parts[0], parts[1], parts[2], parts[3]
                    if not ip.startswith(prefix):
                        continue
                    if hw_type != "0x1" or flag not in ("0x2", "0x6"):
                        continue  # not a complete ARP entry
                    if mac_raw in ("00:00:00:00:00:00", ""):
                        continue
                    results.append((ip, normalize_mac(mac_raw)))
    except (OSError, subprocess.SubprocessError):
        pass

    return results


# ---------------------------------------------------------------------------
# ARP-assisted sweep (L2-first)
# ---------------------------------------------------------------------------

async def ping_host(ip: str, timeout_s: float = 0.5) -> bool:
    """Send one ICMP echo to ip; return True if a reply was received."""
    args = ["ping", "-c", "1", "-W", str(int(timeout_s * 1000))]
    if platform.system() == "Darwin":
        args = ["ping", "-c", "1", "-t", str(int(timeout_s))]
    proc = await asyncio.create_subprocess_exec(
        *args, ip,
        stdout=asyncio.subprocess.DEVNULL,
        stderr=asyncio.subprocess.DEVNULL,
    )
    await proc.wait()
    return proc.returncode == 0


async def sweep_arp_range(
    subnet: str,
    ip_range: range,
    timeout_s: float = 0.5,
    concurrency: int = 20,
) -> list[DiscoveredModule]:
    """Ping-sweep the given range and return field modules found in ARP cache.

    1. Async ping to each IP (fills the kernel ARP cache for responders).
    2. Parse ``arp -an`` / ``/proc/net/arp``.
    3. Filter OUI ``00:24:77``; exclude ``00:30:18`` (IPBox hub).
    4. Return ``DiscoveredModule`` per found IP (mac populated, no HTTP yet).
    """
    sem = asyncio.Semaphore(concurrency)

    async def one(ip: str) -> bool:
        async with sem:
            return await ping_host(ip, timeout_s)

    await asyncio.gather(*[one(f"{subnet}.{i}") for i in ip_range])

    candidates: list[DiscoveredModule] = []
    for ip, mac in parse_arp_table(subnet):
        if is_field_module_mac(mac):
            candidates.append(DiscoveredModule(ip=ip, device_type="unknown", mac=mac))
        # silently skip hub OUI — not a field module

    return candidates


# ---------------------------------------------------------------------------
# HTTP identify (L7)
# ---------------------------------------------------------------------------

def parse_get_sysset_body(text: str) -> dict[str, str]:
    """Parse the body of a ``getSysSet`` HTTP response.

    Handles:
      - JSON object  ``{"ip": "...", "mac": "0.36.119.82.172.190", ...}``
      - key=value lines  ``ip=10.10.1.30\r\nfirm=5.1\r\n``

    Returns a flat dict of field → value (always str), empty on parse failure.
    """
    text = text.strip()
    if not text:
        return {}

    if text.startswith("{"):
        try:
            data: dict[str, Any] = json.loads(text)
            return {str(k): str(v) for k, v in data.items()}
        except json.JSONDecodeError:
            pass

    out: dict[str, str] = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


# -----------------------------------------------------------------------
# Type resolution (devtype → relay/dimmer/input, or model → type fallback)
# -----------------------------------------------------------------------

def device_type_from_fields(fields: dict[str, str]) -> str:
    """Resolve device type from getSysSet fields.

    Cascade:
      1. ``devtype`` field + _DEVTYPE_MAP  (e.g. ``devtype=1`` → relay)
      2. ``name`` field (product label) + _MODEL_TO_TYPE  (e.g. IP200PoE → relay)
      3. ``butLines`` present → input (live JSON often lacks devtype/name)
      4. unknown / unknown_{code}
    """
    raw_devtype = fields.get("devtype", "")
    if raw_devtype in _DEVTYPE_MAP:
        return _DEVTYPE_MAP[raw_devtype]
    if raw_devtype:
        return f"unknown_{raw_devtype}"

    # Fallback: factory product name from getSysSet "name" field
    model_name = fields.get("name", "")
    if model_name in _MODEL_TO_TYPE:
        return _MODEL_TO_TYPE[model_name]

    if fields.get("butLines"):
        return "input"

    return "unknown"


def device_type_from_ref_nr(ref_nr: str) -> str:
    """Map ``device.refNr`` from backupConfig to gateway type."""
    return _MODEL_TO_TYPE.get(ref_nr, "unknown")


def parse_backup_config_body(text: str) -> dict[str, Any] | None:
    """Parse ``backupConfig`` JSON; tolerate control chars in channel descr strings."""
    text = text.strip()
    if not text or not text.startswith("{"):
        return None
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        cleaned = re.sub(r"[\x00-\x1f\x7f]", " ", text)
        try:
            data = json.loads(cleaned)
        except json.JSONDecodeError:
            return None
    return data if isinstance(data, dict) else None


def channels_from_backup_config(data: dict[str, Any]) -> list[dict[str, Any]]:
    """Build channel draft entries from backup ``channels[]`` (relay/dimmer)."""
    out: list[dict[str, Any]] = []
    raw = data.get("channels")
    if not isinstance(raw, list):
        return out
    for entry in raw:
        if not isinstance(entry, dict):
            continue
        ch_id = entry.get("id")
        if ch_id is None:
            continue
        try:
            ch_num = int(ch_id)
        except (TypeError, ValueError):
            continue
        name = str(entry.get("descr", "") or "").strip()
        room = str(entry.get("gr", "") or "").strip()
        if not name and not room:
            continue
        out.append({
            "ch": ch_num,
            "name": name or f"Ch {ch_num}",
            "room": room,
        })
    return out


def apply_backup_config(module: DiscoveredModule, data: dict[str, Any]) -> None:
    """Enrich module from backupConfig (refNr, type, channel labels)."""
    device = data.get("device")
    ref_nr = ""
    if isinstance(device, dict):
        ref_nr = str(device.get("refNr", "") or "").strip()

    if ref_nr:
        module.model = ref_nr
        mapped = device_type_from_ref_nr(ref_nr)
        if mapped != "unknown":
            module.device_type = mapped

    if module.device_type in ("relay", "dimmer"):
        module.channels = channels_from_backup_config(data)


# -----------------------------------------------------------------------
# HTTP identify
# -----------------------------------------------------------------------

async def _http_get_text(
    ip: str,
    method: str,
    sess: aiohttp.ClientSession,
    timeout: float,
) -> str | None:
    url = f"http://{ip}/api.html?method={method}"
    try:
        async with sess.get(url, timeout=aiohttp.ClientTimeout(total=timeout)) as resp:
            if resp.status != 200:
                return None
            return await resp.text()
    except Exception:
        return None


async def http_identify_module(
    ip: str,
    timeout: float = 2.0,
    use_backup_config: bool = True,
) -> DiscoveredModule | None:
    """GET getSysSet (+ optional backupConfig) and return a ``DiscoveredModule``.

    getSysSet: MAC, firmware, devtype/name/butLines heuristics.
    backupConfig: ``device.refNr`` → model/type; ``channels[]`` labels for relay/dimmer.
    """
    try:
        async with aiohttp.ClientSession() as sess:
            return await _http_identify_with_session(
                ip, sess, timeout, use_backup_config=use_backup_config,
            )
    except Exception:
        return None


async def _http_identify_with_session(
    ip: str,
    sess: aiohttp.ClientSession,
    timeout: float,
    *,
    use_backup_config: bool,
) -> DiscoveredModule | None:
    sysset_text = await _http_get_text(ip, "getSysSet", sess, timeout)
    if sysset_text is None:
        return None

    fields = parse_get_sysset_body(sysset_text)
    device_type = device_type_from_fields(fields)
    firmware = fields.get("firm", fields.get("firmware", ""))
    model = fields.get("name", "")

    mac_raw = fields.get("mac", "")
    mac_hex = ""
    if mac_raw and "." in mac_raw:
        parts = mac_raw.split(".")
        if len(parts) == 6:
            mac_hex = ":".join(f"{int(p):02x}" for p in parts)

    module = DiscoveredModule(
        ip=ip,
        device_type=device_type,
        firmware=firmware,
        mac=mac_hex,
        model=model,
    )

    if use_backup_config:
        backup_text = await _http_get_text(ip, "backupConfig", sess, timeout)
        if backup_text:
            backup_data = parse_backup_config_body(backup_text)
            if backup_data:
                apply_backup_config(module, backup_data)

    return module


async def sweep_http_range(
    subnet: str = "10.10.1",
    ip_range: range = MODULE_IP_RANGE,
    *,
    use_backup_config: bool = True,
) -> list[DiscoveredModule]:
    """Concurrently probe all IPs in range via HTTP; return responding modules."""
    tasks = [
        http_identify_module(f"{subnet}.{i}", use_backup_config=use_backup_config)
        for i in ip_range
    ]
    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


# ---------------------------------------------------------------------------
# Orchestrator
# ---------------------------------------------------------------------------

async def discover_modules(
    subnet: str = "10.10.1",
    ip_range: range = MODULE_IP_RANGE,
    arp_first: bool = True,
    ping_timeout: float = 0.5,
    http_timeout: float = 2.0,
    ping_concurrency: int = 20,
    use_backup_config: bool = True,
) -> list[DiscoveredModule]:
    """Discover field modules.

    When ``arp_first=True`` (default):
      1. Ping-sweep the range to populate the kernel ARP cache.
      2. Read the ARP table and filter OUI 00:24:77.
      3. HTTP-identify (getSysSet + backupConfig) only the ARP candidates.
      4. Fall back to full HTTP sweep if no ARP candidates were found.

    When ``arp_first=False``:
      1. Full HTTP sweep of the range (original behaviour).
    """
    if arp_first:
        arp_candidates = await sweep_arp_range(
            subnet, ip_range,
            timeout_s=ping_timeout,
            concurrency=ping_concurrency,
        )
        if arp_candidates:
            # HTTP-identify each ARP candidate in parallel
            tasks = [
                _http_identify_candidate(
                    c, http_timeout, use_backup_config=use_backup_config,
                )
                for c in arp_candidates
            ]
            identified = await asyncio.gather(*tasks)
            return [m for m in identified if m is not None]

        # No ARP candidates — fall back to HTTP-only sweep
        return await sweep_http_range(subnet, ip_range, use_backup_config=use_backup_config)

    return await sweep_http_range(subnet, ip_range, use_backup_config=use_backup_config)


async def _http_identify_candidate(
    module: DiscoveredModule,
    http_timeout: float,
    *,
    use_backup_config: bool = True,
) -> DiscoveredModule | None:
    """Re-identify an ARP candidate via HTTP, preserving its mac."""
    identified = await http_identify_module(
        module.ip,
        timeout=http_timeout,
        use_backup_config=use_backup_config,
    )
    if identified is None:
        return DiscoveredModule(ip=module.ip, device_type="unknown", mac=module.mac)
    # Preserve MAC from ARP (more reliable than getSysSet JSON field)
    if module.mac:
        identified.mac = module.mac
    # Preserve model from ARP when HTTP doesn't provide one
    if not identified.model:
        identified.model = module.model
    return identified


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
# Output builder
# ---------------------------------------------------------------------------

def build_devices_json_draft(modules: list[DiscoveredModule]) -> dict[str, Any]:
    """Assemble a ``devices.json`` draft from discovered modules.

    Channels may be seeded from backupConfig (descr/gr); no ipbox_id.
    ``entity_id`` is never stored; always derived on-the-fly as
    ``"{ip}:{channel}"`` via :func:`gateway.installation.make_entity_id`.
    The device type is resolved server-side, never encoded in the entity_id.

    For legacy ``ipbox_id`` (REST shim compatibility), use
    ``scripts/discover_from_ipbox.py`` instead.
    """
    return {
        "modules": [
            {
                "name": m.model or m.ip,
                "model": m.model,
                "ip": m.ip,
                "type": m.device_type,
                "firmware": m.firmware,
                "mac": m.mac,
                "channels": list(m.channels),
            }
            for m in modules
        ]
    }