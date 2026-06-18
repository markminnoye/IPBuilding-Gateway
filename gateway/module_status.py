"""HTTP module status hydration — seed device registry on startup.

Relay modules do not expose channel state via UDP poll (``P0000`` is a
pulse echo only).  Dimmer idle replies (``I0154999``) carry no setpoint.
Both module types expose live channel state via ``GET
/api.html?method=statuses`` (see IPBUILDING_KNOWLEDGE.md §2A / §2B).

Called once at gateway startup so the first REST/WS snapshot reflects
the real physical channel state instead of the empty post-restart
registry.  No callbacks are fired: state-changed subscribers are wired
in later, when the gateway API is created.
"""

from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

import aiohttp

from gateway.device_registry import DeviceRegistry
from gateway.installation import InstallationConfig
from gateway.module_metadata import _http_get_text
from gateway.types import DeviceKey, DeviceType

log = logging.getLogger(__name__)


def parse_statuses_payload(
    text: str, device_type: DeviceType
) -> dict[int, int]:
    """Parse ``statuses`` JSON into channel → status value.

    Relay: ``0`` = off, ``1`` = on.
    Dimmer: ``0`` = off, ``1``–``100`` = brightness percent.

    Returns an empty dict on parse failure or empty body.
    """
    text = text.strip()
    if not text:
        return {}
    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        log.warning("statuses parse error for %s", device_type.value)
        return {}
    if not isinstance(data, list):
        log.warning(
            "statuses unexpected type %s for %s",
            type(data).__name__,
            device_type.value,
        )
        return {}

    out: dict[int, int] = {}
    for entry in data:
        if not isinstance(entry, dict):
            continue
        ch = entry.get("id")
        status = entry.get("status")
        if ch is None or status is None:
            continue
        try:
            out[int(ch)] = int(status)
        except (TypeError, ValueError):
            continue
    return out


def apply_statuses_to_registry(
    registry: DeviceRegistry,
    module_ip: str,
    device_type: DeviceType,
    statuses: dict[int, int],
) -> int:
    """Seed registry entries from parsed HTTP statuses (no callbacks)."""
    updated = 0
    if device_type == DeviceType.RELAY:
        for ch, status in statuses.items():
            state = "on" if status else "off"
            code = "0100" if state == "on" else "0000"
            key = DeviceKey(DeviceType.RELAY, module_ip, ch)
            registry.seed_relay_state(key, state, code)
            updated += 1
    elif device_type == DeviceType.DIMMER:
        for ch, status in statuses.items():
            level = 0 if status <= 0 else min(status, 100)
            key = DeviceKey(DeviceType.DIMMER, module_ip, ch)
            registry.seed_dimmer_state(key, level)
            updated += 1
    return updated


async def hydrate_registry_from_http(
    registry: DeviceRegistry,
    installation: InstallationConfig,
    *,
    timeout: float = 5.0,
) -> int:
    """Fetch ``statuses`` from relay/dimmer modules and seed the registry.

    Called once at gateway startup before the northbound API accepts
    clients, so the first REST/WS snapshot already reflects physical
    channel state.  Inputs are intentionally skipped: button modules
    expose no per-channel state.

    Returns the total number of channels seeded.  Failures are logged
    at WARNING and treated as zero — a stale empty registry is
    preferable to a startup crash.
    """
    targets = [
        mc
        for mc in installation.modules
        if mc.type in (DeviceType.RELAY, DeviceType.DIMMER)
    ]
    if not targets:
        return 0

    connector = aiohttp.TCPConnector(limit=8)
    updated = 0
    async with aiohttp.ClientSession(connector=connector) as sess:
        sem = asyncio.Semaphore(3)

        async def _one(mc: Any) -> int:
            async with sem:
                text = await _http_get_text(mc.ip, "statuses", sess, timeout)
            if text is None:
                return 0
            statuses = parse_statuses_payload(text, mc.type)
            count = apply_statuses_to_registry(
                registry, mc.ip, mc.type, statuses,
            )
            if count:
                log.info(
                    "HTTP statuses %s (%s): seeded %d channel(s)",
                    mc.ip,
                    mc.type.value,
                    count,
                )
            return count

        results = await asyncio.gather(
            *[_one(mc) for mc in targets], return_exceptions=True
        )

    for mc, result in zip(targets, results):
        if isinstance(result, Exception):
            log.warning(
                "HTTP statuses %s (%s) failed: %s: %r",
                mc.ip,
                mc.type.value,
                type(result).__name__,
                result,
            )
            continue
        updated += int(result)

    if updated:
        log.info("Registry hydrated from HTTP statuses (%d channel updates)", updated)
    return updated
