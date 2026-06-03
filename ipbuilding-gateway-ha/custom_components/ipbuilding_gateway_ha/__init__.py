"""IPBuilding Open integration for Home Assistant.

Connects to the ipbuilding-gateway via WebSocket to expose relay, dimmer,
and button devices as HA entities.
"""

from __future__ import annotations

import logging

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator

log = logging.getLogger(__name__)


async def async_setup_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Set up IPBuilding Open from a config entry."""
    coordinator = IPBuildingCoordinator(hass, entry)
    entry.async_on_unload(entry.add_update_listener(_async_update_listener))
    hass.data.setdefault(DOMAIN, {})[entry.entry_id] = coordinator
    await coordinator.async_config_entry_first_refresh()
    await coordinator.start()
    await hass.config_entries.async_forward_entry_setups(
        entry,
        ["light", "switch", "button", "sensor"],
    )
    return True


async def async_unload_entry(hass: HomeAssistant, entry: ConfigEntry) -> bool:
    """Unload a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN].pop(entry.entry_id)
    await coordinator.stop()
    await hass.config_entries.async_forward_entry_unload(
        entry,
        ["light", "switch", "button", "sensor"],
    )
    return True


async def _async_update_listener(
    hass: HomeAssistant, entry: ConfigEntry
) -> None:
    """Handle config entry updates."""
    await hass.config_entries.async_reload(entry.entry_id)