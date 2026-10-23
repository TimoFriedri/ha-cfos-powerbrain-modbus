"""Talk to a cFos Power Brain wallbox over Modbus.

A standalone device library built on ``modbus-connection``. It takes a
``ModbusUnit`` and knows nothing about Home Assistant, so it can move to its
own package unchanged.
"""

from __future__ import annotations

from .const import (
    DEFAULT_EVSE_PORT,
    DEFAULT_EVSE_UNIT_ID,
    MAX_CHARGING_CURRENT,
    MIN_CHARGING_CURRENT,
    S0_METER_PORTS,
    S0_METER_UNIT_IDS,
    VENDOR_ID,
)
from .device import CfosS0Meter, CfosWallbox, UnsupportedDeviceError
from .enums import ChargePilotState, PhaseRelay, S0Inputs, S0Phases
from .evse import EvseHealth, EvseMeter, EvseSettings, EvseStatus
from .identity import Identity
from .s0_meter import S0MeterReadings, S0MeterSettings

__all__ = [
    "DEFAULT_EVSE_PORT",
    "DEFAULT_EVSE_UNIT_ID",
    "MAX_CHARGING_CURRENT",
    "MIN_CHARGING_CURRENT",
    "S0_METER_PORTS",
    "S0_METER_UNIT_IDS",
    "VENDOR_ID",
    "CfosS0Meter",
    "CfosWallbox",
    "ChargePilotState",
    "EvseHealth",
    "EvseMeter",
    "EvseSettings",
    "EvseStatus",
    "Identity",
    "PhaseRelay",
    "S0Inputs",
    "S0MeterReadings",
    "S0MeterSettings",
    "S0Phases",
    "UnsupportedDeviceError",
]
