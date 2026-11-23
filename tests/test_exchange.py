"""Tests for exchange.py. They load the module by path, so they run without Home Assistant."""

import importlib.util
import json
from pathlib import Path

import pytest

ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location(
    "runscaler_exchange", ROOT / "custom_components" / "runscaler" / "exchange.py"
)
exchange = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(exchange)

CONTRACT = Path(__file__).parent / "fixtures" / "contract"


def load(name: str) -> dict:
    return json.loads((CONTRACT / name).read_text(encoding="utf-8"))


@pytest.fixture
def xdir(tmp_path: Path) -> Path:
    for sub in ("inbox", "outbox", "logs"):
        (tmp_path / sub).mkdir()
    return tmp_path


def test_config_request_matches_contract():
    fixture = load("request-config.json")
    req = exchange.new_request(exchange.KIND_CONFIG, config=fixture["config"])
    assert set(req) == set(fixture)
    assert req["config"] == fixture["config"]
    assert exchange.validate_config(req["config"]) is None


@pytest.mark.parametrize(
    ("name", "action"),
    [("request-restart.json", exchange.ACTION_RESTART), ("request-stop-now.json", exchange.ACTION_STOP_NOW)],
)
def test_action_request_matches_contract(name, action):
    fixture = load(name)
    req = exchange.new_request(exchange.KIND_ACTION, action=action)
    assert set(req) == set(fixture)
    assert req["kind"] == fixture["kind"] and req["action"] == fixture["action"]


def test_request_id_and_time_format():
    req = exchange.new_request(exchange.KIND_ACTION, action=exchange.ACTION_RESTART)
    assert len(req["id"]) <= 64 and req["id"].replace("-", "").isalnum()
    assert req["createdAt"].endswith("Z") and len(req["createdAt"]) == 20


def test_config_request_drops_extra_keys():
    config = {**load("request-config.json")["config"], "dind": True}
    req = exchange.new_request(exchange.KIND_CONFIG, config=config)
    assert "dind" not in req["config"]


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("url", "https://evil.example/x/y"),
        ("name", "Bad Name"),
        ("maxRunners", 3),
        ("maxRunners", True),
        ("dockerMemoryMb", 4096),
        ("runnerImage", "docker.io/library/alpine:3"),
        ("drainTimeout", "31m"),
        ("drainTimeout", "30s"),
        ("drainTimeout", "abc"),
        ("logLevel", "trace"),
    ],
)
def test_validate_rejects(field, value):
    config = {**load("request-config.json")["config"], field: value}
    assert exchange.validate_config(config).startswith(field)


def test_validate_rejects_missing_or_extra_fields():
    config = load("request-config.json")["config"]
    assert exchange.validate_config({**config, "dind": True}) is not None
    del config["url"]
    assert exchange.validate_config(config) is not None


def test_parse_duration():
    assert exchange.parse_duration("30m") == 1800
    assert exchange.parse_duration("1m30s") == 90
    assert exchange.parse_duration("1h") == 3600
    assert exchange.parse_duration("30") is None
    assert exchange.parse_duration("") is None


def test_unknown_kind_or_action():
    with pytest.raises(ValueError):
        exchange.new_request("key")
    with pytest.raises(ValueError):
        exchange.new_request(exchange.KIND_ACTION, action="reboot")


def test_write_request_atomic_and_never_overwrites(xdir: Path):
    first = exchange.new_request(exchange.KIND_ACTION, action=exchange.ACTION_RESTART)
    exchange.write_request(xdir, first)
    assert json.loads((xdir / "inbox" / "request.json").read_text()) == first

    second = exchange.new_request(exchange.KIND_ACTION, action=exchange.ACTION_STOP_NOW)
    with pytest.raises(exchange.RequestPendingError):
        exchange.write_request(xdir, second)
    assert json.loads((xdir / "inbox" / "request.json").read_text()) == first
    assert sorted(p.name for p in (xdir / "inbox").iterdir()) == ["request.json"]


def test_read_json(xdir: Path):
    path = xdir / "outbox" / "result.json"
    assert exchange.read_result(xdir) is None
    path.write_text("{not json")
    assert exchange.read_result(xdir) is None
    path.write_text("[1]")
    assert exchange.read_result(xdir) is None
    path.write_text('{"id": "a", "ok": true}')
    assert exchange.read_result(xdir) == {"id": "a", "ok": True}
    path.write_text('{"x": "' + "a" * exchange.MAX_JSON_BYTES + '"}')
    assert exchange.read_result(xdir) is None


def test_tail_log(xdir: Path):
    assert exchange.tail_log(xdir) == []
    log = xdir / "logs" / "runner.log"
    log.write_text("".join(f"line {i}\n" for i in range(100)))
    assert exchange.tail_log(xdir, 3) == ["line 97", "line 98", "line 99"]


def test_tail_log_large_file_drops_cut_line(xdir: Path):
    log = xdir / "logs" / "runner.log"
    line = "x" * 99 + "\n"
    log.write_text(line * 2000)  # 200 KB, more than LOG_TAIL_BYTES
    lines = exchange.tail_log(xdir, 10_000)
    assert lines and all(len(item) == 99 for item in lines)
    assert len(lines) <= exchange.LOG_TAIL_BYTES // 100
