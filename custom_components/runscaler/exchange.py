"""File contract with runscaler's internal/inbox.

Pure Python, no Home Assistant import, so it can be tested on its own.
The format is defined in the runscaler fork, internal/inbox/testdata/contract/.
runscaler validates every request again: the checks here only fail fast.
"""

from __future__ import annotations

from datetime import UTC, datetime
import json
import os
from pathlib import Path
import re
from typing import Any
import uuid

KIND_CONFIG = "config"
KIND_ACTION = "action"
ACTION_RESTART = "restart"
ACTION_STOP_NOW = "stop-now"

MAX_JSON_BYTES = 64 * 1024
LOG_TAIL_BYTES = 64 * 1024
LOG_LINES = 50

# Same allowlist and ranges as internal/inbox/fields.go.
URL_PATTERN = r"^https://github\.com/[A-Za-z0-9-]+/[A-Za-z0-9._-]+$"
NAME_PATTERN = r"^[a-z0-9-]{1,40}$"
RUNNER_IMAGE_PATTERN = r"^ghcr\.io/actions/actions-runner:[0-9]+\.[0-9]+\.[0-9]+$"
LOG_LEVELS = ("debug", "info", "warn", "error")
INT_RANGES: dict[str, tuple[int, int]] = {
    "maxRunners": (1, 2),
    "concurrent": (1, 2),
    "minRunners": (0, 1),
    "dockerMemoryMb": (256, 1536),
    "dockerCpu": (1, 4),
    "dockerPidsLimit": (64, 4096),
}
DRAIN_MIN_SECONDS = 60
DRAIN_MAX_SECONDS = 30 * 60
EDITABLE_FIELDS = (
    "url",
    "name",
    "maxRunners",
    "concurrent",
    "minRunners",
    "dockerMemoryMb",
    "dockerCpu",
    "dockerPidsLimit",
    "runnerImage",
    "drainTimeout",
    "logLevel",
)

_DURATION_PART = re.compile(r"(\d+)(h|m|s)")
_DURATION_UNITS = {"h": 3600, "m": 60, "s": 1}


class RequestPendingError(Exception):
    """A request is already waiting in inbox/."""


def parse_duration(value: str) -> int | None:
    """Parse a Go duration made of h, m and s parts ("30m", "1m30s") into seconds."""
    if not isinstance(value, str) or not value:
        return None
    parts = _DURATION_PART.findall(value)
    if "".join(n + u for n, u in parts) != value:
        return None
    return sum(int(n) * _DURATION_UNITS[u] for n, u in parts)


def validate_config(config: dict[str, Any]) -> str | None:
    """Return the first error for an editable config, or None when it is valid."""
    if set(config) != set(EDITABLE_FIELDS):
        return "config: must have exactly the editable fields"
    for field, pattern in (
        ("url", URL_PATTERN),
        ("name", NAME_PATTERN),
        ("runnerImage", RUNNER_IMAGE_PATTERN),
    ):
        if not isinstance(config[field], str) or not re.fullmatch(pattern, config[field]):
            return f"{field}: must match {pattern}"
    for field, (low, high) in INT_RANGES.items():
        value = config[field]
        if isinstance(value, bool) or not isinstance(value, int) or not low <= value <= high:
            return f"{field}: must be between {low} and {high}"
    seconds = parse_duration(config["drainTimeout"])
    if seconds is None or not DRAIN_MIN_SECONDS <= seconds <= DRAIN_MAX_SECONDS:
        return "drainTimeout: must be a duration between 1m and 30m"
    if config["logLevel"] not in LOG_LEVELS:
        return "logLevel: must be debug, info, warn or error"
    return None


def new_request(
    kind: str, *, config: dict[str, Any] | None = None, action: str | None = None
) -> dict[str, Any]:
    """Build a request in the shape internal/inbox decodes (unknown keys are rejected)."""
    request: dict[str, Any] = {
        "id": str(uuid.uuid4()),
        "kind": kind,
        "createdAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
    }
    if kind == KIND_CONFIG:
        if config is None:
            raise ValueError("config request needs a config")
        request["config"] = {field: config[field] for field in EDITABLE_FIELDS}
    elif kind == KIND_ACTION:
        if action not in (ACTION_RESTART, ACTION_STOP_NOW):
            raise ValueError(f"unknown action {action!r}")
        request["action"] = action
    else:
        raise ValueError(f"unknown kind {kind!r}")
    return request


def write_request(exchange_dir: Path, request: dict[str, Any]) -> None:
    """Write inbox/request.json atomically; never replace a pending request."""
    inbox = exchange_dir / "inbox"
    final = inbox / "request.json"
    tmp = inbox / f".request.json.tmp-{request['id']}"
    tmp.write_text(json.dumps(request, indent=2) + "\n", encoding="utf-8")
    try:
        # link() fails if request.json exists, so a pending request is never overwritten.
        os.link(tmp, final)
    except FileExistsError as err:
        raise RequestPendingError from err
    finally:
        tmp.unlink(missing_ok=True)


def read_json(path: Path) -> dict[str, Any] | None:
    """Read a small JSON object; None when the file is missing, too big or invalid."""
    try:
        with path.open("rb") as file:
            data = file.read(MAX_JSON_BYTES + 1)
    except FileNotFoundError:
        return None
    if len(data) > MAX_JSON_BYTES:
        return None
    try:
        value = json.loads(data)
    except ValueError:
        return None
    return value if isinstance(value, dict) else None


def read_current_config(exchange_dir: Path) -> dict[str, Any] | None:
    return read_json(exchange_dir / "outbox" / "current-config.json")


def read_result(exchange_dir: Path) -> dict[str, Any] | None:
    return read_json(exchange_dir / "outbox" / "result.json")


def tail_log(exchange_dir: Path, lines: int = LOG_LINES) -> list[str]:
    """Return the last lines of logs/runner.log, reading at most LOG_TAIL_BYTES."""
    path = exchange_dir / "logs" / "runner.log"
    try:
        with path.open("rb") as file:
            size = file.seek(0, os.SEEK_END)
            start = max(0, size - LOG_TAIL_BYTES)
            file.seek(start)
            data = file.read()
    except FileNotFoundError:
        return []
    text = data.decode("utf-8", errors="replace").splitlines()
    if start > 0 and text:
        text = text[1:]  # the first line was cut in the middle
    return [line for line in text if line][-lines:]
