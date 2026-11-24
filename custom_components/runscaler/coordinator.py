"""Polls runscaler and sends it requests."""

from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
import logging
from pathlib import Path
from typing import Any

import aiohttp

from homeassistant.components import persistent_notification
from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.aiohttp_client import async_get_clientsession
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed
from homeassistant.util import dt as dt_util

from . import exchange
from .const import (
    CONF_EXCHANGE_DIR,
    CONF_HEALTH_URL,
    DOMAIN,
    EVENT_REQUEST_FINISHED,
    HEALTH_TIMEOUT,
    REQUEST_TIMEOUT,
    SCAN_INTERVAL,
)

_LOGGER = logging.getLogger(__name__)


async def async_fetch_health(session: aiohttp.ClientSession, url: str) -> dict[str, Any] | None:
    """GET /healthz; None when runscaler is down or answers something unexpected."""
    try:
        async with asyncio.timeout(HEALTH_TIMEOUT):
            async with session.get(url) as resp:
                resp.raise_for_status()
                data = await resp.json(content_type=None)
    except (aiohttp.ClientError, TimeoutError, ValueError):
        return None
    return data if isinstance(data, dict) else None


@dataclass
class RunscalerData:
    health: dict[str, Any] | None
    current: dict[str, Any] | None  # outbox/current-config.json
    result: dict[str, Any] | None  # outbox/result.json
    log_lines: list[str] = field(default_factory=list)

    @property
    def scale_set(self) -> dict[str, Any]:
        sets = (self.health or {}).get("scale_sets") or [{}]
        return sets[0] if isinstance(sets[0], dict) else {}

    @property
    def metrics(self) -> dict[str, Any]:
        return self.scale_set.get("metrics") or {}


class RunscalerCoordinator(DataUpdateCoordinator[RunscalerData]):
    """Reads /healthz and the exchange directory every SCAN_INTERVAL."""

    config_entry: ConfigEntry

    def __init__(self, hass: HomeAssistant, entry: ConfigEntry) -> None:
        super().__init__(
            hass, _LOGGER, config_entry=entry, name=DOMAIN, update_interval=SCAN_INTERVAL
        )
        self.health_url: str = entry.data[CONF_HEALTH_URL]
        self.exchange_dir = Path(entry.data[CONF_EXCHANGE_DIR])
        self._session = async_get_clientsession(hass)
        # Editable config as the user is changing it; sent only by apply_config().
        self.draft: dict[str, Any] | None = None
        self._draft_base: str | None = None  # writtenAt of the snapshot the draft started from
        self._pending: dict[str, Any] | None = None
        self.last_request: dict[str, Any] = {}

    def _read_files(self) -> tuple[dict | None, dict | None, list[str]]:
        return (
            exchange.read_current_config(self.exchange_dir),
            exchange.read_result(self.exchange_dir),
            exchange.tail_log(self.exchange_dir),
        )

    async def _async_update_data(self) -> RunscalerData:
        health = await async_fetch_health(self._session, self.health_url)
        current, result, lines = await self.hass.async_add_executor_job(self._read_files)
        if health is None and current is None:
            raise UpdateFailed(f"runscaler not reachable at {self.health_url} and no snapshot")
        data = RunscalerData(health=health, current=current, result=result, log_lines=lines)

        if current and current.get("writtenAt") != self._draft_base:
            self.draft = dict(current.get("config") or {})
            self._draft_base = current.get("writtenAt")
        self._track_request(result)
        return data

    def _track_request(self, result: dict[str, Any] | None) -> None:
        if self._pending is None:
            if not self.last_request and result:
                self.last_request = _from_result(result, kind=None)
            return
        if result and result.get("id") == self._pending["id"]:
            self._finish(_from_result(result, kind=self._pending["kind"]))
        elif dt_util.utcnow() - self._pending["sent_at"] > REQUEST_TIMEOUT:
            self._finish(
                {
                    "state": "timeout",
                    "id": self._pending["id"],
                    "kind": self._pending["kind"],
                    "error": "runscaler did not answer in time",
                    "finished_at": None,
                }
            )

    def _finish(self, outcome: dict[str, Any]) -> None:
        self._pending = None
        self.last_request = outcome
        self.hass.bus.async_fire(EVENT_REQUEST_FINISHED, {**outcome, "ok": outcome["state"] == "applied"})
        if outcome["state"] != "applied":
            persistent_notification.async_create(
                self.hass,
                f"Request {outcome['kind']} was {outcome['state']}: {outcome['error']}",
                title="Runscaler",
                notification_id=f"{DOMAIN}_request",
            )

    @property
    def pending_changes(self) -> bool:
        if not self.data or not self.data.current or self.draft is None:
            return False
        return self.draft != self.data.current.get("config")

    def set_draft(self, key: str, value: Any) -> None:
        if self.draft is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_snapshot")
        self.draft[key] = value
        self.async_update_listeners()

    def discard_draft(self) -> None:
        if self.data and self.data.current:
            self.draft = dict(self.data.current.get("config") or {})
        self.async_update_listeners()

    async def async_apply_config(self) -> None:
        if self.draft is None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="no_snapshot")
        if error := exchange.validate_config(self.draft):
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_config",
                translation_placeholders={"error": error},
            )
        await self._async_submit(exchange.new_request(exchange.KIND_CONFIG, config=self.draft))

    async def async_action(self, action: str) -> None:
        await self._async_submit(exchange.new_request(exchange.KIND_ACTION, action=action))

    async def _async_submit(self, request: dict[str, Any]) -> None:
        if self._pending is not None:
            raise HomeAssistantError(translation_domain=DOMAIN, translation_key="request_pending")
        try:
            await self.hass.async_add_executor_job(
                exchange.write_request, self.exchange_dir, request
            )
        except exchange.RequestPendingError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN, translation_key="request_pending"
            ) from err
        except OSError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        self._pending = {"id": request["id"], "kind": request["kind"], "sent_at": dt_util.utcnow()}
        self.last_request = {
            "state": "pending",
            "id": request["id"],
            "kind": request["kind"],
            "error": None,
            "finished_at": None,
        }
        self.async_update_listeners()


def _from_result(result: dict[str, Any], kind: str | None) -> dict[str, Any]:
    return {
        "state": "applied" if result.get("ok") else "rejected",
        "id": result.get("id"),
        "kind": kind,
        "error": result.get("error"),
        "finished_at": result.get("finishedAt"),
    }
