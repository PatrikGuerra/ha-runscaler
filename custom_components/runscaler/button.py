"""Buttons: apply or discard the config draft, restart, stop now."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import RunscalerConfigEntry
from .coordinator import RunscalerCoordinator
from .entity import RunscalerEntity
from .exchange import ACTION_RESTART, ACTION_STOP_NOW


async def _discard(c: RunscalerCoordinator) -> None:
    c.discard_draft()


@dataclass(frozen=True, kw_only=True)
class RunscalerButtonDescription(ButtonEntityDescription):
    press_fn: Callable[[RunscalerCoordinator], Awaitable[None]]


BUTTONS = (
    RunscalerButtonDescription(
        key="apply_config",
        translation_key="apply_config",
        entity_category=EntityCategory.CONFIG,
        press_fn=lambda c: c.async_apply_config(),
    ),
    RunscalerButtonDescription(
        key="discard_changes",
        translation_key="discard_changes",
        entity_category=EntityCategory.CONFIG,
        press_fn=_discard,
    ),
    RunscalerButtonDescription(
        key="restart",
        translation_key="restart",
        press_fn=lambda c: c.async_action(ACTION_RESTART),
    ),
    RunscalerButtonDescription(
        key="stop_now",
        translation_key="stop_now",
        press_fn=lambda c: c.async_action(ACTION_STOP_NOW),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: RunscalerConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    coordinator = entry.runtime_data
    async_add_entities(RunscalerButton(coordinator, d) for d in BUTTONS)


class RunscalerButton(RunscalerEntity, ButtonEntity):
    entity_description: RunscalerButtonDescription

    def __init__(self, coordinator: RunscalerCoordinator, description: RunscalerButtonDescription) -> None:
        super().__init__(coordinator, description, Platform.BUTTON)

    async def async_press(self) -> None:
        await self.entity_description.press_fn(self.coordinator)
