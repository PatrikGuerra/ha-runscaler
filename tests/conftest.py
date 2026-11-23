"""Shared fixtures for the Home Assistant tests (pytest-homeassistant-custom-component)."""

import json
from pathlib import Path

import pytest

HEALTH_URL = "http://127.0.0.1:8089/healthz"
CONTRACT = Path(__file__).parent / "fixtures" / "contract"

HEALTH = {
    "status": "ok",
    "version": "v0.23.0-ha.1",
    "uptime": "1h",
    "scale_sets": [
        {
            "name": "orangepi3",
            "ready": True,
            "idle": 0,
            "busy": 0,
            "metrics": {"jobs_started": 3, "jobs_completed": 2, "desired_runners": 1, "assigned_jobs": 1, "running_jobs": 1},
        }
    ],
    "disk": [{"filesystem": "/", "free_percent": 88.4, "free_bytes": 1, "total_bytes": 2}],
}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations):
    yield


@pytest.fixture
def current_config() -> dict:
    return json.loads((CONTRACT / "request-config.json").read_text(encoding="utf-8"))["config"]


@pytest.fixture
def exchange_dir(tmp_path: Path, current_config: dict) -> Path:
    for sub in ("inbox", "outbox", "logs"):
        (tmp_path / sub).mkdir()
    (tmp_path / "outbox" / "current-config.json").write_text(
        json.dumps(
            {
                "config": current_config,
                "readOnly": {"clientId": "Iv23test", "installationId": 1, "runscalerVersion": "v0.23.0-ha.1"},
                "writtenAt": "2026-11-23T15:00:05Z",
            }
        )
    )
    (tmp_path / "logs" / "runner.log").write_text("first line\nlast line\n")
    return tmp_path
