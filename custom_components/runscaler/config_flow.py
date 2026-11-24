"""Config flow: where runscaler's /healthz and exchange directory are."""

from __future__ import annotations

from pathlib import Path
from typing import Any

import voluptuous as vol

from homeassistant.config_entries import ConfigFlow, ConfigFlowResult
from homeassistant.helpers.aiohttp_client import async_get_clientsession

from . import exchange
from .const import CONF_EXCHANGE_DIR, CONF_HEALTH_URL, DEFAULT_EXCHANGE_DIR, DEFAULT_HEALTH_URL, DOMAIN
from .coordinator import async_fetch_health


class RunscalerConfigFlow(ConfigFlow, domain=DOMAIN):
    VERSION = 1

    async def async_step_user(self, user_input: dict[str, Any] | None = None) -> ConfigFlowResult:
        errors: dict[str, str] = {}
        if user_input is not None:
            await self.async_set_unique_id(user_input[CONF_EXCHANGE_DIR])
            self._abort_if_unique_id_configured()
            health = await async_fetch_health(
                async_get_clientsession(self.hass), user_input[CONF_HEALTH_URL]
            )
            current = await self.hass.async_add_executor_job(
                exchange.read_current_config, Path(user_input[CONF_EXCHANGE_DIR])
            )
            if health is None:
                errors["base"] = "cannot_connect"
            elif current is None:
                errors["base"] = "no_snapshot"
            else:
                name = (current.get("config") or {}).get("name") or "Runscaler"
                return self.async_create_entry(title=name, data=user_input)

        defaults = user_input or {
            CONF_HEALTH_URL: DEFAULT_HEALTH_URL,
            CONF_EXCHANGE_DIR: DEFAULT_EXCHANGE_DIR,
        }
        schema = vol.Schema(
            {
                vol.Required(CONF_HEALTH_URL, default=defaults[CONF_HEALTH_URL]): str,
                vol.Required(CONF_EXCHANGE_DIR, default=defaults[CONF_EXCHANGE_DIR]): str,
            }
        )
        return self.async_show_form(step_id="user", data_schema=schema, errors=errors)
