"""Button entity platform for IPBuilding Open.

Exposes physical buttons on IP1100PoE modules as HA EventEntity
instances. Each button press from the gateway triggers a
`button_pressed` event in Home Assistant.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.event import EventEntity, EventEntityDescription
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator

log = logging.getLogger(__name__)

_BUTTON_EVENT_TYPES = ["press"]


class IPBuildingEventButton(EventEntity):
    """A hardware button exposed as a Home Assistant EventEntity.

    Fires ``ipbuilding_gateway_ha.button_pressed`` events when the gateway
    receives a button press from the IP1100PoE.
    """

    _attr_has_entity_name = True
    _attr_event_types = _BUTTON_EVENT_TYPES

    def __init__(
        self,
        hardware_id: str,
        name: str | None,
        coordinator: IPBuildingCoordinator,
        device_info: dict[str, Any],
    ) -> None:
        self._hardware_id = hardware_id
        self._coordinator = coordinator
        self._attr_unique_id = f"event_{hardware_id}"
        self._attr_device_info = device_info
        self.entity_description = EventEntityDescription(
            name=name or f"Button {hardware_id}",
            event_types=_BUTTON_EVENT_TYPES,
            translation_key="button",
            translation_placeholders={"hardware_id": hardware_id},
        )
        self._on_button_event: Callable[[dict], None] | None = None

    async def async_added_to_hass(self) -> None:
        """Register to receive button events from the coordinator."""
        listener_key = f"button:{self._hardware_id}"

        @callback
        def callback(data: dict) -> None:
            self.async_trigger_event(
                "button_pressed",
                {"hardware_id": self._hardware_id, "action": data.get("action", "press")},
            )

        self._on_button_event = callback
        self._coordinator.register_entity(listener_key, callback)

    async def async_will_remove_from_hass(self) -> None:
        """Unregister the button event listener."""
        if self._on_button_event is not None:
            self._coordinator.unregister_entity(
                f"button:{self._hardware_id}", self._on_button_event
            )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up button/event entities from a config entry.

    Creates an IPBuildingEventButton for each entry in devices.json that
    represents a physical button (type=input on IP1100PoE).
    """
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data if isinstance(coordinator.data, dict) else {}

    buttons = []
    for entity_id, device in devices.items():
        # Only create buttons for input channels.
        # The device type is encoded in the entity_id as "ip:type:ch"
        parts = entity_id.split(":")
        device_type = parts[1] if len(parts) == 3 else None
        if device_type == "input":
            hardware_id = device["id"]
            name = device.get("name")
            device_info = {
                "identifiers": {(DOMAIN, hardware_id)},
                "name": name or f"Button {hardware_id}",
                "manufacturer": "IPBuilding",
                "model": "IP1100PoE",
            }
            buttons.append(IPBuildingEventButton(hardware_id, name, coordinator, device_info))

    async_add_entities(buttons)