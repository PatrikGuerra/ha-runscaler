"""Binary sensors: reachable, connected to GitHub, unsaved config changes."""

from __future__ import annotations

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator
from .entity import RunscalerEntity

REACHABLE = BinarySensorEntityDescription(
    key="reachable", translation_key="reachable", device_class=BinarySensorDeviceClass.CONNECTIVITY
)
CONNECTED = BinarySensorEntityDescription(
    key="connected", translation_key="connected", device_class=BinarySensorDeviceClass.CONNECTIVITY
)
PENDING_CHANGES = BinarySensorEntityDescription(
    key="pending_changes", translation_key="pending_changes"
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(
        RunscalerBinarySensor(coordinator, d) for d in (REACHABLE, CONNECTED, PENDING_CHANGES)
    )


class RunscalerBinarySensor(RunscalerEntity, BinarySensorEntity):
    def __init__(self, coordinator: RunscalerCoordinator, description: BinarySensorEntityDescription) -> None:
        super().__init__(coordinator, description, Platform.BINARY_SENSOR)

    @property
    def available(self) -> bool:
        if self.entity_description.key == CONNECTED.key:
            return super().available and self.coordinator.data.health is not None
        return super().available

    @property
    def is_on(self) -> bool:
        data = self.coordinator.data
        match self.entity_description.key:
            case "reachable":
                return data.health is not None
            case "connected":
                return bool(data.scale_set.get("ready"))
        return self.coordinator.pending_changes
