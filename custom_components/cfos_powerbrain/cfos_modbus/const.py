"""Constants of the cFos Power Brain Wallbox's Modbus interface."""

from __future__ import annotations

from typing import Final

VENDOR_ID: Final = 0xCF05
"""The vendor id every cFos device reports in registers 8000-8001."""

DEFAULT_EVSE_PORT: Final = 4701
DEFAULT_EVSE_UNIT_ID: Final = 1

S0_METER_PORTS: Final = {1: 4702, 2: 4703}
"""Modbus TCP port of each S0 meter input, keyed by input number."""

S0_METER_UNIT_IDS: Final = {1: 2, 2: 3}
"""Default slave id of each S0 meter input, keyed by input number."""

MIN_CHARGING_CURRENT: Final = 6.0
"""Lowest charging current IEC 61851 allows a wallbox to signal, in A."""

MAX_CHARGING_CURRENT: Final = 63.0
"""Highest current the registers accept, in A; most models cap lower."""

WAKE_UP_SECONDS: Final = 5
"""How long a wake-up interrupts the control pilot, in s."""
