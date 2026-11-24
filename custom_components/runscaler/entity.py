"""Base entity: one device per config entry, stable entity ids."""

from __future__ import annotations

from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .const import DOMAIN
from .coordinator import RunscalerCoordinator


class RunscalerEntity(CoordinatorEntity[RunscalerCoordinator]):
    _attr_has_entity_name = True

    def __init__(
        self, coordinator: RunscalerCoordinator, description: EntityDescription, platform: str
    ) -> None:
        super().__init__(coordinator)
        self.entity_description = description
        entry_id = coordinator.config_entry.entry_id
        self._attr_unique_id = f"{entry_id}_{description.key}"
        # English ids whatever the UI language, so dashboards and automations can name them.
        self.entity_id = f"{platform}.{DOMAIN}_{description.key}"
        self._attr_device_info = DeviceInfo(
            identifiers={(DOMAIN, entry_id)},
            name="Runscaler",
            manufacturer="runscaler",
            configuration_url="https://github.com/PatrikGuerra/runscaler",
        )
