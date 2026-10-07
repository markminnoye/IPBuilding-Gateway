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

log = logging.getLogger(__name__)

SUPERVISOR_CORE_API = "http://supervisor/core/api"
NOTIFICATION_ID = "ipbuilding_gateway_remote_debugging"
NOTIFICATION_TITLE = "Remote debugging and control"
NOTIFICATION_MESSAGE = (
    "Remote debugging and control is ON. Anyone on your network can read "
    "field-bus traffic and send raw packets to your IPBuilding modules via "
    "this gateway. Turn it off in the add-on configuration when you are done."
)


def _service_payload(enabled: bool) -> tuple[str, dict[str, Any]]:
    if enabled:
        return "create", {
            "notification_id": NOTIFICATION_ID,
            "title": NOTIFICATION_TITLE,
            "message": NOTIFICATION_MESSAGE,
        }
    return "dismiss", {"notification_id": NOTIFICATION_ID}


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
    service, payload = _service_payload(enabled)
    if not token:
        log.warning(
            "Remote debugging notification skipped (%s): SUPERVISOR_TOKEN is not set",
            service,
        )
        return

    url = f"{SUPERVISOR_CORE_API}/services/persistent_notification/{service}"
    headers = {"Authorization": f"Bearer {token}"}
    timeout = aiohttp.ClientTimeout(total=5)
    owns_session = session is None
    if session is None:
        session = aiohttp.ClientSession()
    try:
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
