"""Sensor entity platform for IPBuilding Open.

Exposes power readings (current_watt) from state_changed events
as sensor entities with DeviceClass.POWER.
"""

from __future__ import annotations

import logging
from typing import Any, Callable

from homeassistant.components.sensor import SensorEntity, SensorEntityDescription
from homeassistant.components.sensor.const import SensorDeviceClass
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddEntitiesCallback
from homeassistant.const import UnitOfPower

from .const import DOMAIN
from .coordinator import IPBuildingCoordinator

log = logging.getLogger(__name__)


def _make_power_description(device: dict[str, Any]) -> SensorEntityDescription:
    """Build a SensorEntityDescription for a power sensor."""
    return SensorEntityDescription(
        key=f"{device['id']}_power",
        name=f"{device.get('name', device['id'])} Power",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=None,
        original_icon="mdi:flash",
    )


class IPBuildingPowerSensor(SensorEntity):
    """A power sensor reporting current_watt from the gateway.

    Updated whenever the gateway emits a state_changed event for the
    associated entity_id.
    """

    _attr_has_entity_name = True
    _attr_native_unit_of_measurement = UnitOfPower.WATT
    _attr_device_class = SensorDeviceClass.POWER

    def __init__(
        self,
        device: dict[str, Any],
        coordinator: IPBuildingCoordinator,
    ) -> None:
        self._device = device
        self._coordinator = coordinator
        self._entity_id = device["id"]
        self._attr_unique_id = f"{device['id']}_power"
        self._attr_device_info = {
            "identifiers": {(DOMAIN, device["id"])},
            "name": device.get("name", device["id"]),
            "manufacturer": "IPBuilding",
            "model": device.get("device_type", "unknown"),
        }
        self.entity_description = _make_power_description(device)
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
        """Update the sensor value from a gateway state_changed message."""
        self._attr_native_value = state.get("current_watt", 0)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: ConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up power sensor entities from a config entry."""
    coordinator: IPBuildingCoordinator = hass.data[DOMAIN][entry.entry_id]
    devices = coordinator.data if isinstance(coordinator.data, dict) else {}

    sensors = []
    for entity_id, device in devices.items():
        # Only expose power sensors for relay and dimmer devices.
        device_type = device.get("device_type")
        if device_type in ("relay", "dimmer"):
            sensors.append(IPBuildingPowerSensor(device, coordinator))

    async_add_entities(sensors)