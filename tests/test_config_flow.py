"""Config flow tests."""

from pathlib import Path

from custom_components.runscaler.const import CONF_EXCHANGE_DIR, CONF_HEALTH_URL, DOMAIN
from homeassistant import config_entries
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType

from .conftest import HEALTH, HEALTH_URL


async def start(hass: HomeAssistant, exchange_dir: Path):
    result = await hass.config_entries.flow.async_init(DOMAIN, context={"source": config_entries.SOURCE_USER})
    assert result["type"] is FlowResultType.FORM
    return await hass.config_entries.flow.async_configure(
        result["flow_id"], {CONF_HEALTH_URL: HEALTH_URL, CONF_EXCHANGE_DIR: str(exchange_dir)}
    )


async def test_creates_entry(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    result = await start(hass, exchange_dir)
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "orangepi3"


async def test_health_down(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, status=503)
    result = await start(hass, exchange_dir)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}


async def test_no_snapshot(hass: HomeAssistant, aioclient_mock, tmp_path: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    result = await start(hass, tmp_path)
    assert result["errors"] == {"base": "no_snapshot"}
