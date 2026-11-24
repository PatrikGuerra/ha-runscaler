"""Sensors from /healthz, the log and the last request."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.typing import StateType

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator, RunscalerData
from .entity import RunscalerEntity

MAX_STATE = 255


def _disk_free(data: RunscalerData) -> StateType:
    disks = (data.health or {}).get("disk") or []
    return disks[0].get("free_percent") if disks and isinstance(disks[0], dict) else None


def _clip(value: Any) -> StateType:
    return str(value)[:MAX_STATE] if value else None


@dataclass(frozen=True, kw_only=True)
class RunscalerSensorDescription(SensorEntityDescription):
    value_fn: Callable[[RunscalerData], StateType]
    needs_health: bool = True


SENSORS = (
    RunscalerSensorDescription(
        key="status", translation_key="status", value_fn=lambda d: (d.health or {}).get("status")
    ),
    # busy stays 0 while a job runs; assigned/running jobs are the live signal.
    RunscalerSensorDescription(
        key="assigned_jobs",
        translation_key="assigned_jobs",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.metrics.get("assigned_jobs", 0),
    ),
    RunscalerSensorDescription(
        key="running_jobs",
        translation_key="running_jobs",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.metrics.get("running_jobs", 0),
    ),
    RunscalerSensorDescription(
        key="idle_runners",
        translation_key="idle_runners",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda d: d.scale_set.get("idle", 0),
    ),
    # These reset when runscaler restarts; total_increasing treats that as a reset.
    RunscalerSensorDescription(
        key="jobs_started",
        translation_key="jobs_started",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.metrics.get("jobs_started"),
    ),
    RunscalerSensorDescription(
        key="jobs_completed",
        translation_key="jobs_completed",
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda d: d.metrics.get("jobs_completed"),
    ),
    RunscalerSensorDescription(
        key="disk_free",
        translation_key="disk_free",
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=0,
        value_fn=_disk_free,
    ),
    RunscalerSensorDescription(
        key="last_error",
        translation_key="last_error",
        value_fn=lambda d: _clip(d.scale_set.get("last_error")),
    ),
    RunscalerSensorDescription(
        key="version",
        translation_key="version",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda d: (d.health or {}).get("version"),
    ),
    RunscalerSensorDescription(
        key="last_log_line",
        translation_key="last_log_line",
        needs_health=False,
        value_fn=lambda d: _clip(d.log_lines[-1] if d.log_lines else None),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    entities: list[SensorEntity] = [RunscalerSensor(coordinator, d) for d in SENSORS]
    entities.append(LastRequestSensor(coordinator))
    async_add_entities(entities)


class RunscalerSensor(RunscalerEntity, SensorEntity):
    entity_description: RunscalerSensorDescription
    # The log tail would bloat the recorder database.
    _unrecorded_attributes = frozenset({"lines"})

    def __init__(self, coordinator: RunscalerCoordinator, description: RunscalerSensorDescription) -> None:
        super().__init__(coordinator, description, Platform.SENSOR)

    @property
    def available(self) -> bool:
        if not super().available:
            return False
        return not self.entity_description.needs_health or self.coordinator.data.health is not None

    @property
    def native_value(self) -> StateType:
        return self.entity_description.value_fn(self.coordinator.data)

    @property
    def extra_state_attributes(self) -> dict[str, Any] | None:
        if self.entity_description.key == "last_log_line":
            return {"lines": self.coordinator.data.log_lines}
        return None


class LastRequestSensor(RunscalerEntity, SensorEntity):
    def __init__(self, coordinator: RunscalerCoordinator) -> None:
        super().__init__(
            coordinator,
            SensorEntityDescription(
                key="last_request",
                translation_key="last_request",
                device_class=SensorDeviceClass.ENUM,
                options=["pending", "applied", "rejected", "timeout"],
            ),
            Platform.SENSOR,
        )

    @property
    def available(self) -> bool:
        return self.coordinator.last_update_success

    @property
    def native_value(self) -> StateType:
        return self.coordinator.last_request.get("state")

    @property
    def extra_state_attributes(self) -> dict[str, Any]:
        r = self.coordinator.last_request
        return {k: r.get(k) for k in ("id", "kind", "error", "finished_at")}
