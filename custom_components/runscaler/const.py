"""Constants for the Runscaler integration."""

from datetime import timedelta

DOMAIN = "runscaler"

CONF_HEALTH_URL = "health_url"
CONF_EXCHANGE_DIR = "exchange_dir"

DEFAULT_HEALTH_URL = "http://127.0.0.1:8089/healthz"
DEFAULT_EXCHANGE_DIR = "/runscaler-exchange"

SCAN_INTERVAL = timedelta(seconds=10)
HEALTH_TIMEOUT = 5  # seconds
# runscaler runs `runner validate`, which calls the GitHub API, before it answers.
REQUEST_TIMEOUT = timedelta(seconds=120)

EVENT_REQUEST_FINISHED = "runscaler_request_finished"
