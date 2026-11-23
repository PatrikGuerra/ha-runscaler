"""Log level of the editable config. It changes the draft, not runscaler."""

from __future__ import annotations

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator
from .entity import RunscalerEntity
from .exchange import LOG_LEVELS

LOG_LEVEL = SelectEntityDescription(
    key="log_level",
    translation_key="log_level",
    options=list(LOG_LEVELS),
    entity_category=EntityCategory.CONFIG,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    async_add_entities([RunscalerLogLevel(entry.runtime_data)])


class RunscalerLogLevel(RunscalerEntity, SelectEntity):
    def __init__(self, coordinator: RunscalerCoordinator) -> None:
        super().__init__(coordinator, LOG_LEVEL, Platform.SELECT)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.draft is not None

    @property
    def current_option(self) -> str | None:
        return self.coordinator.draft.get("logLevel")

    async def async_select_option(self, option: str) -> None:
        self.coordinator.set_draft("logLevel", option)
