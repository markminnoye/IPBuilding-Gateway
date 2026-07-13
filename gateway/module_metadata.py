"""Module metadata cache — live HTTP read of getSysSet and getButtons.

Fetched once at gateway startup and on explicit POST /api/v1/modules/refresh
(or POST /api/v1/modules/{module_id}/refresh for a single module).
Does NOT persist to devices.json; network/button data is runtime-only.
"""

from __future__ import annotations

import asyncio
import logging
from dataclasses import dataclass, field
from typing import Any

import aiohttp

from gateway.health import GatewayHealthMonitor
from gateway.installation import InstallationConfig, ModuleConfig
from gateway.types import DeviceType

log = logging.getLogger(__name__)


def normalize_button_hardware_id(raw_id: str) -> str:
    """Canonicalise an IP1100PoE button hardware id for northbound routing.

    ``getButtons`` returns ids like ``2D2F8185190000DF`` (2-char type prefix
    plus 14 hex chars). UDP ``B-...E`` frames carry the wire suffix only
    (``2f8185190000df``). Northbound consumers (companion, snapshot) need
    the wire form so a ``button_event.id`` always matches a device entry.
    """
    s = raw_id.strip().lower()
    if len(s) >= 2 and s.startswith("2d"):
        s = s[2:]
    return s


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

    async def refresh_one(
        self,
        mc: ModuleConfig,
        timeout: float = 5.0,
        *,
        sess: aiohttp.ClientSession | None = None,
    ) -> None:
        """Fetch getSysSet (and getButtons for input) for one module.

        Updates ``self._by_mac[mc.mac]`` on success. On failure the previous
        cache entry is kept when available.
        """
        if not mc.mac:
            log.debug("Skipping refresh for %s - no MAC", mc.ip)
            return

        mac = mc.mac
        close_sess = False
        if sess is None:
            connector = aiohttp.TCPConnector(limit=2)
            sess = aiohttp.ClientSession(connector=connector)
            close_sess = True

        try:
            try:
                result = await _http_get_text(mc.ip, "getSysSet", sess, timeout)
            except Exception as exc:
                log.warning(
                    "getSysSet %s (%s) failed: %s: %r",
                    mc.ip, mac, type(exc).__name__, exc,
                )
                if self._health is not None:
                    self._health.report_issue(
                        f"module_metadata.getSysSet.{mc.ip}",
                        "module_metadata.http_failed",
                        "warning",
                        f"getSysSet {mc.ip} ({mac}) failed: {type(exc).__name__}: {exc!r}",
                        {"ip": mc.ip, "method": "getSysSet"},
                    )
                return

            if result is None:
                if self._health is not None:
                    self._health.report_issue(
                        f"module_metadata.getSysSet.{mc.ip}",
                        "module_metadata.http_failed",
                        "warning",
                        f"HTTP getSysSet {mc.ip} failed",
                        {"ip": mc.ip, "method": "getSysSet"},
                    )
                return

            if self._health is not None:
                self._health.clear_issue(f"module_metadata.getSysSet.{mc.ip}")

            meta = ModuleMetadata()
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
                meta.buttons = await _fetch_buttons(mc.ip, timeout, self._health)

            meta.fetched_at = _iso_now()
            self._by_mac[mac] = meta
        finally:
            if close_sess:
                await sess.close()

    async def refresh(self, installation: InstallationConfig, timeout: float = 5.0) -> None:
        """Fetch getSysSet (all) and getButtons (input only).

        Requests are fanned out with bounded concurrency (3 in flight at
        a time) to avoid flooding a small /24 subnet when the cache is
        refreshed during discovery bursts.

        Partial failure is logged; entries for failed modules keep their old cache.
        """
        connector = aiohttp.TCPConnector(limit=8)
        async with aiohttp.ClientSession(connector=connector) as sess:
            sem = asyncio.Semaphore(3)

            async def _bounded(mc: ModuleConfig) -> None:
                async with sem:
                    await self.refresh_one(mc, timeout, sess=sess)

            await asyncio.gather(
                *[
                    asyncio.create_task(_bounded(mc), name=f"refresh:{mc.mac}")
                    for mc in installation.modules
                    if mc.mac
                ],
                return_exceptions=True,
            )

        install_macs = {mc.mac for mc in installation.modules if mc.mac}
        self._by_mac = {
            mac: meta for mac, meta in self._by_mac.items() if mac in install_macs
        }
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


# ---------------------------------------------------------------------------
# PushbuttonConfig extraction
# ---------------------------------------------------------------------------


def extract_pushbutton_config(
    module_id: str,
    button_json: dict[str, Any],
    default_threshold_s: float | None = None,
):
    """Convert a raw getButtons entry into a :class:`PushbuttonConfig`.

    ``channel`` is read from the wire ``"index"`` field. The hold threshold
    is seeded from ``func2.holdSeconds`` when present — this is the same
    drempelwaarde the IPBox hanteert for its long_press detection
    (operator-bevestigd 2026-06-16, IPBUILDING_KNOWLEDGE.md §12.7).
    """
    from gateway.installation import DEFAULT_BUTTON_HOLD_THRESHOLD_S, PushbuttonConfig

    raw_id = button_json.get("id")
    if not raw_id:
        raise ValueError(f"button entry has no 'id': {button_json!r}")
    btn_id = normalize_button_hardware_id(str(raw_id))

    func2 = button_json.get("func2") or {}
    hold = func2.get("holdSeconds")
    try:
        hold_s = float(hold) if hold is not None else (
            default_threshold_s if default_threshold_s is not None
            else DEFAULT_BUTTON_HOLD_THRESHOLD_S
        )
    except (TypeError, ValueError):
        hold_s = (
            default_threshold_s if default_threshold_s is not None
            else DEFAULT_BUTTON_HOLD_THRESHOLD_S
        )

    return PushbuttonConfig(
        id=btn_id,
        module_id=module_id,
        channel=button_json.get("index"),
        name=button_json.get("descr", "") or button_json.get("name", ""),
        room=button_json.get("gr", "") or button_json.get("room", ""),
        active=True,
        hold_threshold_s=hold_s,
    )


def extract_pushbuttons_from_getbuttons(
    module_id: str, buttons_json: list[dict[str, Any]]
) -> list:
    """Apply :func:`extract_pushbutton_config` to a full getButtons list.

    Skips entries that fail to parse (logged at WARNING); the caller still
    gets a partial list back. Used by the runtime auto-discovery to seed
    missing PushbuttonConfig entries into ``devices.json`` (Fase 8 hook).
    """
    from gateway.installation import PushbuttonConfig

    out: list[PushbuttonConfig] = []
    for entry in buttons_json or []:
        try:
            out.append(extract_pushbutton_config(module_id, entry))
        except ValueError as exc:
            log.warning("Skipping getButtons entry: %s", exc)
    return out


def _iso_now() -> str:
    from datetime import datetime, timezone

    return datetime.now(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
