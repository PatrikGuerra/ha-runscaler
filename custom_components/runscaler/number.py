"""Numeric fields of the editable config. They change the draft, not runscaler."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import NumberEntity, NumberEntityDescription, NumberMode
from homeassistant.const import EntityCategory, Platform, UnitOfInformation, UnitOfTime
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator
from .entity import RunscalerEntity
from .exchange import DRAIN_MAX_SECONDS, DRAIN_MIN_SECONDS, INT_RANGES, parse_duration


def _minutes(value: Any) -> float | None:
    seconds = parse_duration(value)
    return None if seconds is None else seconds / 60


@dataclass(frozen=True, kw_only=True)
class RunscalerNumberDescription(NumberEntityDescription):
    field: str
    to_draft: Callable[[float], Any] = int
    from_draft: Callable[[Any], float | None] = lambda v: v


def _int_field(key: str, field: str, step: float = 1, unit: str | None = None) -> RunscalerNumberDescription:
    low, high = INT_RANGES[field]
    return RunscalerNumberDescription(
        key=key,
        translation_key=key,
        field=field,
        native_min_value=low,
        native_max_value=high,
        native_step=step,
        native_unit_of_measurement=unit,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
    )


NUMBERS = (
    _int_field("max_runners", "maxRunners"),
    _int_field("concurrent", "concurrent"),
    _int_field("min_runners", "minRunners"),
    _int_field("docker_memory", "dockerMemoryMb", unit=UnitOfInformation.MEGABYTES),
    _int_field("docker_cpu", "dockerCpu"),
    _int_field("docker_pids_limit", "dockerPidsLimit"),
    RunscalerNumberDescription(
        key="drain_timeout",
        translation_key="drain_timeout",
        field="drainTimeout",
        native_min_value=DRAIN_MIN_SECONDS / 60,
        native_max_value=DRAIN_MAX_SECONDS / 60,
        native_step=1,
        native_unit_of_measurement=UnitOfTime.MINUTES,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        to_draft=lambda v: f"{int(v)}m",
        from_draft=_minutes,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RunscalerNumber(coordinator, d) for d in NUMBERS)


class RunscalerNumber(RunscalerEntity, NumberEntity):
    entity_description: RunscalerNumberDescription

    def __init__(self, coordinator: RunscalerCoordinator, description: RunscalerNumberDescription) -> None:
        super().__init__(coordinator, description, Platform.NUMBER)

    @property
    def available(self) -> bool:
        return super().available and self.coordinator.draft is not None

    @property
    def native_value(self) -> float | None:
        return self.entity_description.from_draft(self.coordinator.draft.get(self.entity_description.field))

    async def async_set_native_value(self, value: float) -> None:
        self.coordinator.set_draft(self.entity_description.field, self.entity_description.to_draft(value))
