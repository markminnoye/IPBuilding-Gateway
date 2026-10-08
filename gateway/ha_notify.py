"""Persistent Home Assistant notification for remote debugging.

Uses the Supervisor proxy to Home Assistant Core
(``homeassistant_api: true``). A missing token or a failed request is logged
and never raised: gateway startup must continue.
"""

from __future__ import annotations

import logging
import os
from typing import Any

import aiohttp

from gateway.remote_debug_copy import notification_message, notification_title

log = logging.getLogger(__name__)

SUPERVISOR_CORE_API = "http://supervisor/core/api"
NOTIFICATION_ID = "ipbuilding_gateway_remote_debugging"


def _service_payload(enabled: bool, language: str) -> tuple[str, dict[str, Any]]:
    if enabled:
        return "create", {
            "notification_id": NOTIFICATION_ID,
            "title": notification_title(language),
            "message": notification_message(language),
        }
    return "dismiss", {"notification_id": NOTIFICATION_ID}


async def _ha_language(session: aiohttp.ClientSession, token: str) -> str:
    """Language from Home Assistant ``/api/config``. English if that fails."""
    url = f"{SUPERVISOR_CORE_API}/config"
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=5)
    try:
        async with session.get(url, headers=headers, timeout=timeout) as resp:
            if resp.status >= 400:
                log.warning(
                    "HA language lookup failed: HTTP %s; notification stays English",
                    resp.status,
                )
                return "en"
            body = await resp.json(content_type=None)
    except Exception:
        log.warning(
            "HA language lookup failed; notification stays English",
            exc_info=True,
        )
        return "en"
    if not isinstance(body, dict):
        return "en"
    language = body.get("language")
    return language if isinstance(language, str) else "en"


async def sync_remote_debugging_notification(
    enabled: bool,
    *,
    token: str | None = None,
    session: aiohttp.ClientSession | None = None,
) -> None:
    """Create the notification when remote debugging is on, dismiss it when off."""
    if token is None:
        token = os.environ.get("SUPERVISOR_TOKEN", "")
    token = token.strip()
    if not token:
        log.warning(
            "Remote debugging notification skipped (%s): SUPERVISOR_TOKEN is not set",
            "create" if enabled else "dismiss",
        )
        return

    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=5)
    owns_session = session is None
    if session is None:
        session = aiohttp.ClientSession()
    service = "create" if enabled else "dismiss"
    try:
        language = await _ha_language(session, token) if enabled else "en"
        service, payload = _service_payload(enabled, language)
        url = f"{SUPERVISOR_CORE_API}/services/persistent_notification/{service}"
        async with session.post(
            url, json=payload, headers=headers, timeout=timeout
        ) as resp:
            if resp.status >= 400:
                log.warning(
                    "Remote debugging notification %s failed: HTTP %s",
                    service,
                    resp.status,
                )
    except Exception:
        log.warning(
            "Remote debugging notification %s failed",
            service,
            exc_info=True,
        )
    finally:
        if owns_session:
            await session.close()
