"""Text fields of the editable config. They change the draft, not runscaler."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.text import TextEntity, TextEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator
from .entity import RunscalerEntity
from .exchange import NAME_PATTERN, RUNNER_IMAGE_PATTERN, URL_PATTERN


@dataclass(frozen=True, kw_only=True)
class RunscalerTextDescription(TextEntityDescription):
    field: str


TEXTS = (
    RunscalerTextDescription(key="url", translation_key="url", field="url", pattern=URL_PATTERN, native_max=200),
    RunscalerTextDescription(key="name", translation_key="name", field="name", pattern=NAME_PATTERN, native_max=40),
    RunscalerTextDescription(
        key="runner_image",
        translation_key="runner_image",
        field="runnerImage",
        pattern=RUNNER_IMAGE_PATTERN,
        native_max=100,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RunscalerText(coordinator, d) for d in TEXTS)


class RunscalerText(RunscalerEntity, TextEntity):
    entity_description: RunscalerTextDescription
    _attr_entity_category = EntityCategory.CONFIG

    def __init__(self, coordinator: RunscalerCoordinator, description: RunscalerTextDescription) -> None:
        super().__init__(coordinator, description, Platform.TEXT)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.draft is not None

    @property
    def native_value(self) -> str | None:
        return self.coordinator.draft.get(self.entity_description.field)

    async def async_set_value(self, value: str) -> None:
        self.coordinator.set_draft(self.entity_description.field, value)
