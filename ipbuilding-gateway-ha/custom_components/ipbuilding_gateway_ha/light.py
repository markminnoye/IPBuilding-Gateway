"""Light entity platform for IPBuilding Open.

Exposes relay channels as ONOFF lights and dimmer channels as
BRIGHTNESS lights based on the semantic_type in devices.json.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.light import ColorMode, LightEntity
from homeassistant.components.light.entity_description import LightEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN, SEMANTIC_TYPE_LIGHT
from .coordinator import IPBuildingCoordinator

log = logging.getLogger(__name__)

# Key in devices.json that indicates a light
_LIGHT_SEMANTIC_TYPES = {SEMANTIC_TYPE_LIGHT}


def _device_to_entity_description(
    device: dict[str, Any], coordinator: IPBuildingCoordinator
) -> LightEntityDescription:
    """Build a LightEntityDescription from a device dict."""
    return LightEntityDescription(
        key=device["id"],
        name=device.get("name", device["id"]),
        device_class=None,
        original_icon="mdi:lightbulb",
    )


class IPBuildingLight(LightEntity):
    """A light entity backed by the IPBuilding Gateway via WebSocket."""

    _attr_has_entity_name = True
    _attr_color_mode = ColorMode.ONOFF
    _attr_supported_color_modes: set[ColorMode] = {ColorMode.ONOFF}
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
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device["id"])},
            "name": device.get("name", device["id"]),
            "manufacturer": "IPBuilding",
            "model": device.get("device_type", "unknown"),
        }
        # Store the update callback so the entity can be notified
        self._on_update: Callable[[dict], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register for updates from the coordinator."""
        # Set initial state from coordinator cache
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
        is_on = state.get("state") in ("on", "ON")
        self._attr_is_on = is_on

        # Dimmer-specific: extract brightness level
        # The device type is encoded in entity_id as "ip:type:ch"
        is_dimmer = self._entity_id.split(":")[1] == "dimmer" if ":" in self._entity_id else False
        if "level" in state and is_dimmer:
            level = state.get("level")
            if level is not None:
                self._attr_brightness = round(255 * level / 100)
                self._attr_color_mode = ColorMode.BRIGHTNESS
                self._attr_supported_color_modes = {ColorMode.BRIGHTNESS, ColorMode.ONOFF}

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Turn the light on."""
        if self._attr_brightness is not None and self._attr_brightness > 0:
            await self._coordinator.async_send_command(
                self._entity_id, "DIM", round(self._attr_brightness * 100 / 255)
            )
        else:
            await self._coordinator.async_send_command(self._entity_id, "ON")

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Turn the light off."""
        await self._coordinator.async_send_command(self._entity_id, "OFF")


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up light entities from a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data if isinstance(coordinator.data, dict) else {}

    lights = []
    for entity_id, device in devices.items():
        if device.get("semantic_type") in _LIGHT_SEMANTIC_TYPES:
            lights.append(IPBuildingLight(device, coordinator))

    async_add_entities(lights)