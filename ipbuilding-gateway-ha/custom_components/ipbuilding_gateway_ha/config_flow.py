"""Config flow for IPBuilding Open.

User provides the gateway host and port, then we validate by
calling GET /api/v1/devices.
"""

from __future__ import annotations

import logging
from typing import Any

import aiohttp
import voluptuous as vol
from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.const import CONF_HOST, CONF_PORT

from .const import DEFAULT_API_PORT, DOMAIN

log = logging.getLogger(__name__)

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_API_PORT): int,
    }
)


async def _validate_gateway(host: str, port: int) -> tuple[bool, str | None]:
    """Check that the gateway is reachable and returns a device list."""
    url = f"http://{host}:{port}/api/v1/devices"
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url, timeout=aiohttp.ClientTimeout(total=5)) as resp:
                if resp.status == 200:
                    try:
                        data = await resp.json()
                        devices = data.get("devices", [])
                        log.info("Gateway validated: %d devices", len(devices))
                        return True, None
                    except Exception as exc:
                        return False, f"Invalid JSON from gateway: {exc}"
                else:
                    return False, f"HTTP {resp.status}"
    except aiohttp.ClientConnectorError:
        return False, "Connection refused — is the gateway running?"
    except Exception as exc:
        return False, str(exc)


class IPBuildingConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for IPBuilding Open."""

    VERSION = 1

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Handle the initial step: ask for host + port."""
        errors: dict[str, str] = {}

        if user_input is not None:
            host = user_input[CONF_HOST]
            port = user_input[CONF_PORT]

            valid, error = await _validate_gateway(host, port)
            if valid:
                return self.async_create_entry(
                    title=f"IPBuilding Gateway ({host})",
                    data=user_input,
                )
            errors["base"] = error or "gateway_unreachable"

        return self.async_show_form(
            step_id="user",
            data_schema=STEP_USER_DATA_SCHEMA,
            errors=errors,
            description_placeholders={"host": user_input.get(CONF_HOST, "") if user_input else ""},
        )