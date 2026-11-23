"""End-to-end tests of the integration against a fake runscaler (files + mocked /healthz)."""

import json
from pathlib import Path

import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from custom_components.runscaler.const import CONF_EXCHANGE_DIR, CONF_HEALTH_URL, DOMAIN
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError

from .conftest import HEALTH, HEALTH_URL


async def setup(hass: HomeAssistant, exchange_dir: Path) -> MockConfigEntry:
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=str(exchange_dir),
        data={CONF_HEALTH_URL: HEALTH_URL, CONF_EXCHANGE_DIR: str(exchange_dir)},
    )
    entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()
    return entry


async def read_request(hass: HomeAssistant, exchange_dir: Path) -> dict:
    path = exchange_dir / "inbox" / "request.json"
    return json.loads(await hass.async_add_executor_job(path.read_text))


async def press(hass: HomeAssistant, entity_id: str) -> None:
    await hass.services.async_call("button", "press", {"entity_id": entity_id}, blocking=True)


async def test_state_entities(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    await setup(hass, exchange_dir)

    assert hass.states.get("binary_sensor.runscaler_reachable").state == "on"
    assert hass.states.get("binary_sensor.runscaler_connected").state == "on"
    assert hass.states.get("sensor.runscaler_assigned_jobs").state == "1"
    assert hass.states.get("sensor.runscaler_running_jobs").state == "1"
    assert hass.states.get("sensor.runscaler_jobs_completed").state == "2"
    assert hass.states.get("sensor.runscaler_disk_free").state == "88.4"
    log = hass.states.get("sensor.runscaler_last_log_line")
    assert log.state == "last line"
    assert log.attributes["lines"] == ["first line", "last line"]
    assert hass.states.get("number.runscaler_docker_memory").state == "1024"
    assert hass.states.get("number.runscaler_drain_timeout").state == "30.0"
    assert hass.states.get("select.runscaler_log_level").state == "info"
    assert hass.states.get("text.runscaler_name").state == "orangepi3"
    assert hass.states.get("binary_sensor.runscaler_pending_changes").state == "off"


async def test_health_down_keeps_config_entities(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, status=500)
    await setup(hass, exchange_dir)

    assert hass.states.get("binary_sensor.runscaler_reachable").state == "off"
    assert hass.states.get("sensor.runscaler_assigned_jobs").state == "unavailable"
    assert hass.states.get("number.runscaler_docker_memory").state == "1024"


async def test_apply_config_writes_full_request(
    hass: HomeAssistant, aioclient_mock, exchange_dir: Path, current_config: dict
):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    entry = await setup(hass, exchange_dir)

    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.runscaler_docker_memory", "value": 768}, blocking=True
    )
    await hass.services.async_call(
        "number", "set_value", {"entity_id": "number.runscaler_drain_timeout", "value": 10}, blocking=True
    )
    assert hass.states.get("binary_sensor.runscaler_pending_changes").state == "on"
    assert not (exchange_dir / "inbox" / "request.json").exists()

    await press(hass, "button.runscaler_apply_config")
    req = await read_request(hass, exchange_dir)
    assert req["kind"] == "config"
    assert req["config"] == {**current_config, "dockerMemoryMb": 768, "drainTimeout": "10m"}
    assert hass.states.get("sensor.runscaler_last_request").state == "pending"

    # A second request while one is pending is refused.
    with pytest.raises(HomeAssistantError):
        await press(hass, "button.runscaler_restart")

    # runscaler answers.
    events = []
    hass.bus.async_listen("runscaler_request_finished", events.append)
    result = exchange_dir / "outbox" / "result.json"
    await hass.async_add_executor_job(
        result.write_text, json.dumps({"id": req["id"], "ok": True, "finishedAt": "2026-11-23T15:01:00Z"})
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    assert hass.states.get("sensor.runscaler_last_request").state == "applied"
    assert events and events[0].data["ok"] is True


async def test_rejected_request_notifies(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    entry = await setup(hass, exchange_dir)

    await press(hass, "button.runscaler_stop_now")
    req = await read_request(hass, exchange_dir)
    assert req["kind"] == "action" and req["action"] == "stop-now"

    result = exchange_dir / "outbox" / "result.json"
    await hass.async_add_executor_job(
        result.write_text,
        json.dumps({"id": req["id"], "ok": False, "error": "boom", "finishedAt": "2026-11-23T15:01:00Z"}),
    )
    await entry.runtime_data.async_refresh()
    await hass.async_block_till_done()
    state = hass.states.get("sensor.runscaler_last_request")
    assert state.state == "rejected"
    assert state.attributes["error"] == "boom"


async def test_invalid_draft_is_not_sent(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    entry = await setup(hass, exchange_dir)

    entry.runtime_data.set_draft("runnerImage", "docker.io/library/alpine:3")
    with pytest.raises(HomeAssistantError):
        await press(hass, "button.runscaler_apply_config")
    assert not (exchange_dir / "inbox" / "request.json").exists()

    await press(hass, "button.runscaler_discard_changes")
    assert hass.states.get("binary_sensor.runscaler_pending_changes").state == "off"


async def test_unload(hass: HomeAssistant, aioclient_mock, exchange_dir: Path):
    aioclient_mock.get(HEALTH_URL, json=HEALTH)
    entry = await setup(hass, exchange_dir)
    assert await hass.config_entries.async_unload(entry.entry_id)
