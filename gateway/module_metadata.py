"""Module metadata cache — live HTTP read of getSysSet and getButtons.

Fetched once at gateway startup and on explicit POST /api/v1/modules/refresh.
Does NOT persist to devices.json; network/button data is runtime-only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from gateway.health import GatewayHealthMonitor
from gateway.installation import InstallationConfig
from gateway.types import DeviceType

log = logging.getLogger(__name__)


def _parse_get_sysset_body(text: str) -> dict[str, str]:
    """Parse getSysSet HTTP response body.

    Handles JSON ``{"ip": "...", "mac": "0.36.119.82.172.190"}``
    and key=value lines ``ip=10.10.1.30``.
    Returns a flat dict of field -> value (always str), empty on failure.
    """
    import json

    text = text.strip()
    if not text:
        return {}
    if text.startswith("{"):
        try:
            data = json.loads(text)
            return {str(k): str(v) for k, v in data.items()}
        except Exception:
            pass
    out = {}
    for line in text.splitlines():
        if "=" in line:
            k, _, v = line.partition("=")
            out[k.strip()] = v.strip()
    return out


async def _http_get_text(
    ip: str, method: str, sess: aiohttp.ClientSession, timeout: float
) -> str | None:
    """GET http://{ip}/api.html?method={method} and return text or None."""
    url = f"http://{ip}/api.html?method={method}"
    try:
        async with sess.get(
            url, timeout=aiohttp.ClientTimeout(total=timeout)
        ) as resp:
            if resp.status == 200:
                return await resp.text()
            log.warning("HTTP %s %s -> status %s", method, ip, resp.status)
    except Exception as exc:
        # Include the exception class and repr — some aiohttp/OSError
        # exceptions have an empty str(), which used to log a bare
        # "failed:" line with no diagnostic info.
        log.warning(
            "HTTP %s %s failed: %s: %r",
            method, ip, type(exc).__name__, exc,
        )
    return None


@dataclass
class ModuleMetadata:
    """Runtime metadata for one module, fetched via HTTP."""

    network: dict[str, str] = field(default_factory=dict)
    button: str = ""
    allow: str = ""
    buttons: list[dict[str, Any]] | None = None
    fetched_at: str | None = None


class ModuleMetadataCache:
    """In-memory cache of getSysSet (+ getButtons for input modules) per module MAC."""

    def __init__(self, health: GatewayHealthMonitor | None = None) -> None:
        self._by_mac: dict[str, ModuleMetadata] = {}
        self._health = health

    def get(self, mac: str) -> ModuleMetadata | None:
        return self._by_mac.get(mac)

    def all_macs(self) -> list[str]:
        return list(self._by_mac.keys())

    async def refresh(self, installation: InstallationConfig, timeout: float = 2.0) -> None:
        """Fetch getSysSet (all) and getButtons (input only) in parallel.

        Partial failure is logged; entries for failed modules keep their old cache.
        """
        async with aiohttp.ClientSession() as sess:
            pending: dict[str, tuple[Any, asyncio.Task[str | None]]] = {}

            for mc in installation.modules:
                if not mc.mac:
                    log.debug("Skipping refresh for %s - no MAC", mc.ip)
                    continue
                task = asyncio.create_task(
                    _http_get_text(mc.ip, "getSysSet", sess, timeout),
                    name=f"getSysSet:{mc.mac}",
                )
                pending[mc.mac] = (mc, task)

            results = await asyncio.gather(
                *[t for _, t in pending.values()], return_exceptions=True
            )

        now = _iso_now()
        new_by_mac: dict[str, ModuleMetadata] = {}

        for (mac, (mc, _task)), result in zip(pending.items(), results):
            meta = ModuleMetadata()

            if isinstance(result, Exception):
                log.warning(
                    "getSysSet %s (%s) failed: %s: %r",
                    mc.ip, mac, type(result).__name__, result,
                )
                if self._health is not None:
                    self._health.report_issue(
                        f"module_metadata.getSysSet.{mc.ip}",
                        "module_metadata.http_failed",
                        "warning",
                        f"getSysSet {mc.ip} ({mac}) failed: {type(result).__name__}: {result!r}",
                        {"ip": mc.ip, "method": "getSysSet"},
                    )
                existing = self._by_mac.get(mac)
                if existing:
                    new_by_mac[mac] = existing
                continue

            if result is None:
                if self._health is not None:
                    self._health.report_issue(
                        f"module_metadata.getSysSet.{mc.ip}",
                        "module_metadata.http_failed",
                        "warning",
                        f"HTTP getSysSet {mc.ip} failed",
                        {"ip": mc.ip, "method": "getSysSet"},
                    )
                # HTTP failed: keep old cache entry if available, otherwise skip.
                existing = self._by_mac.get(mac)
                if existing:
                    new_by_mac[mac] = existing
                continue

            if self._health is not None:
                self._health.clear_issue(f"module_metadata.getSysSet.{mc.ip}")

            fields = _parse_get_sysset_body(result)
            network: dict[str, str] = {}
            for k in ("dhcp", "ip", "subnet", "gateway"):
                v = fields.get(k, "")
                if v:
                    network[k] = v
            meta.network = network
            meta.button = fields.get("button", "")
            meta.allow = fields.get("allow", "")

            if mc.type == DeviceType.INPUT:
                buttons = await _fetch_buttons(mc.ip, timeout, self._health)
                meta.buttons = buttons

            meta.fetched_at = now
            new_by_mac[mac] = meta

        self._by_mac = new_by_mac
        log.info("ModuleMetadataCache refreshed %d modules", len(self._by_mac))


async def _fetch_buttons(
    module_ip: str, timeout: float, health: GatewayHealthMonitor | None = None
) -> list[dict[str, Any]] | None:
    """Fetch getButtons JSON array from an input module."""
    import json

    async with aiohttp.ClientSession() as sess:
        text = await _http_get_text(module_ip, "getButtons", sess, timeout)
    if text is None:
        if health is not None:
            health.report_issue(
                f"module_metadata.getButtons.{module_ip}",
                "module_metadata.http_failed",
                "warning",
                f"HTTP getButtons {module_ip} failed",
                {"ip": module_ip, "method": "getButtons"},
            )
        return None
    if health is not None:
        health.clear_issue(f"module_metadata.getButtons.{module_ip}")
    try:
        data = json.loads(text)
        if isinstance(data, list):
            return data
        log.warning("getButtons %s unexpected type %s", module_ip, type(data).__name__)
    except Exception as exc:
        log.warning("getButtons %s parse error: %s", module_ip, exc)
    return None


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
