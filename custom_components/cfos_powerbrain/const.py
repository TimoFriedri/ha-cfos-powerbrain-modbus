"""Constants for the cFos Power Brain integration."""

from __future__ import annotations

from datetime import timedelta
from typing import Final

DOMAIN: Final = "cfos_powerbrain"
MANUFACTURER: Final = "cFos"
DEFAULT_NAME: Final = "cFos Power Brain"

CONF_UNIT_ID: Final = "unit_id"
CONF_S0_METERS: Final = "s0_meters"

DEFAULT_SCAN_INTERVAL: Final = 10
"""Seconds between two reads of the live values."""

MIN_SCAN_INTERVAL: Final = 1
MAX_SCAN_INTERVAL: Final = 30
"""Stays well below the wallbox's default 300 s Modbus fail-safe timeout."""

SETTINGS_SCAN_INTERVAL: Final = timedelta(minutes=5)

MAX_CURRENT_SETTING: Final = 32.0
"""Highest current offered in the UI, in A; the registers would take 63."""
