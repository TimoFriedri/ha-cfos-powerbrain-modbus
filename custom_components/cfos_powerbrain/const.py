"""Constants for the cFos Power Brain Wallbox integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cfos_powerbrain"
MANUFACTURER: Final = "cFos"
DEFAULT_NAME: Final = "cFos Power Brain Wallbox"

FORMER_DEFAULT_NAME: Final = "cFos Power Brain"
"""The default title before 0.3.0, renamed by the config entry migration."""

CONF_UNIT_ID: Final = "unit_id"
CONF_S0_METERS: Final = "s0_meters"
CONF_CHARGING_MANAGER: Final = "charging_manager"
CONF_CHARGING_MANAGER_PORT: Final = "charging_manager_port"
CONF_CHARGING_MANAGER_UNIT_ID: Final = "charging_manager_unit_id"

DEFAULT_SCAN_INTERVAL: Final = 10
"""Seconds between two reads of the live values."""

MIN_SCAN_INTERVAL: Final = 1
MAX_SCAN_INTERVAL: Final = 30
"""Stays well below the wallbox's default 300 s Modbus fail-safe timeout."""

SETTINGS_SCAN_INTERVAL: Final = timedelta(minutes=5)

MAX_CURRENT_SETTING: Final = 32.0
"""Highest current offered in the UI, in A; the registers would take 63."""
