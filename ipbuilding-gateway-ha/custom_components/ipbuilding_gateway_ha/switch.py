"""Switch entity platform for IPBuilding Open.

Exposes relay/dimmer channels with semantic_type in (switch, plug, fan)
as HA switch entities.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.switch import SwitchEntity
from homeassistant.components.switch.entity_description import SwitchEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SEMANTIC_TYPE_FAN, SEMANTIC_TYPE_PLUG, SEMANTIC_TYPE_SWITCH
from .coordinator import IPBuildingCoordinator

log = logging.getLogger(__name__)

_SWITCH_SEMANTIC_TYPES = {SEMANTIC_TYPE_SWITCH, SEMANTIC_TYPE_PLUG, SEMANTIC_TYPE_FAN}


def _make_device_info(device: dict[str, Any]) -> dict[str, Any]:
    """Build device_info dict from a device dict."""
    return {
        "identifiers": {(DOMAIN, device["id"])},
        "name": device.get("name", device["id"]),
        "manufacturer": "IPBuilding",
        "model": device.get("device_type", "unknown"),
    }


class IPBuildingSwitch(SwitchEntity):
    """A switch entity backed by the IPBuilding Gateway via WebSocket."""

    _attr_has_entity_name = True
    _attr_is_on: bool | None = None

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: IPBuildingCoordinator,
    ) -> None:
        self._device = device
        self._coordinator = coordinator
        self._entity_id = device["id"]
        self._attr_unique_id = device["id"]
        self._attr_device_info = _make_device_info(device)
        self._on_update: Callable[[dict], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for updates from the coordinator."""
        state = self._coordinator.get_device_state(self._entity_id)
        if state:
            self._update_from_state(state)

        def callback(data: dict) -> None:
            self._update_from_state(data)
            self.async_write_ha_state()

        self._on_update = callback
        self._coordinator.register_entity(self._entity_id, callback)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the update callback."""
        if self._on_update is not None:
            self._coordinator.unregister_entity(self._entity_id, self._on_update)

    def _update_from_state(self, state: dict) -> None:
        """Update entity state from a gateway state_changed message."""
        self._attr_is_on = state.get("state") in ("on", "ON")

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the switch on."""
        await self._coordinator.async_send_command(self._entity_id, "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the switch off."""
        await self._coordinator.async_send_command(self._entity_id, "OFF")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up switch entities from a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data if isinstance(coordinator.data, dict) else {}

    switches = []
    for entity_id, device in devices.items():
        if device.get("semantic_type") in _SWITCH_SEMANTIC_TYPES:
            switches.append(IPBuildingSwitch(device, coordinator))

    async_add_entities(switches)