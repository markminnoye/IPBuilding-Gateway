"""Config flow for IPBuilding Open.

Auto-detects the ipbuilding_gateway HA add-on via the Supervisor API.
Falls back to manual host/port entry for standalone Docker or remote gateways.
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

ADDON_SLUG = "ipbuilding_gateway"
ADDON_API_PORT = 8080

STEP_USER_DATA_SCHEMA = vol.Schema(
    {
        vol.Required(CONF_HOST): str,
        vol.Required(CONF_PORT, default=DEFAULT_API_PORT): int,
    }
)


async def _supervisor_addon_info(hass) -> dict[str, Any] | None:
    """Query Supervisor for ipbuilding_gateway add-on info. Returns None if not found."""
    try:
        # hassio is available on HA OS / Supervised
        import homeassistant.components.hassio as hassio_mod
        addon = hassio_mod.HassIO(hass)
        info = await hass.async_add_executor_job(addon.get_addon_info, ADDON_SLUG)
        return info
    except Exception as exc:
        log.debug("Supervisor add-on check failed: %s", exc)
        return None


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
        """Handle the initial step.

        Attempt Supervisor auto-detection first. If the add-on is running,
        pre-fill and validate automatically. Otherwise fall back to manual entry.
        """
        errors: dict[str, str] = {}

        # Attempt 1: supervisor auto-detection
        if user_input is None:
            addon_info = await _supervisor_addon_info(self.hass)
            if addon_info and addon_info.get("state") == "started":
                host = "127.0.0.1"
                port = addon_info.get("port", ADDON_API_PORT)
                log.info("Add-on detected via Supervisor at %s:%s", host, port)
                valid, error = await _validate_gateway(host, port)
                if valid:
                    return self.async_create_entry(
                        title=f"IPBuilding Gateway (add-on)",
                        data={CONF_HOST: host, CONF_PORT: port},
                    )
                log.info("Add-on found but gateway not reachable: %s", error)
                errors["base"] = f"Add-on running but gateway unreachable: {error}"
            elif addon_info is None:
                log.info("Not running under Supervisor — proceeding to manual entry")
            else:
                log.info("Add-on not running (state=%s) — proceeding to manual entry",
                         addon_info.get("state"))

        # Fallback / manual entry
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
            description_placeholders={
                "host": user_input.get(CONF_HOST, "") if user_input else ""
            },
        )