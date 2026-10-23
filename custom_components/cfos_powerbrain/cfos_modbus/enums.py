"""Coded register values of the cFos Power Brain Wallbox."""

from __future__ import annotations

from enum import IntEnum, IntFlag


class ChargePilotState(IntEnum):
    """IEC 61851 control pilot state, register 8092."""

    WAITING = 0
    """A: no vehicle connected."""

    VEHICLE_DETECTED = 1
    """B: vehicle connected, not charging."""

    CHARGING = 2
    """C: charging."""

    CHARGING_VENTILATION = 3
    """D: charging with ventilation required."""

    NO_POWER = 4
    """E: no power available on the control pilot."""

    ERROR = 5
    """F: error."""

    DC_SENSOR_ERROR = 9
    """The DC residual current sensor reports a fault."""

    @property
    def vehicle_connected(self) -> bool:
        """Whether a vehicle is plugged in."""
        return self in _CONNECTED

    @property
    def charging(self) -> bool:
        """Whether the vehicle draws current."""
        return self in _CHARGING

    @property
    def problem(self) -> bool:
        """Whether the state is a fault."""
        return self in _PROBLEM


_CHARGING = frozenset(
    {ChargePilotState.CHARGING, ChargePilotState.CHARGING_VENTILATION}
)
_CONNECTED = _CHARGING | {ChargePilotState.VEHICLE_DETECTED}
_PROBLEM = frozenset(
    {
        ChargePilotState.NO_POWER,
        ChargePilotState.ERROR,
        ChargePilotState.DC_SENSOR_ERROR,
    }
)


def charge_pilot_state(raw: int) -> ChargePilotState:
    """Decode register 8092; the register map defines every other code as error."""
    try:
        return ChargePilotState(raw)
    except ValueError:
        return ChargePilotState.ERROR


class PhaseRelay(IntEnum):
    """Which contactor charges the vehicle, register 8087."""

    THREE_PHASE = 0
    SINGLE_PHASE = 1


class S0Inputs(IntFlag):
    """Hardware status bits, register 8113."""

    S0_INPUT_1 = 1 << 0
    S0_INPUT_2 = 1 << 1
    PHASE_SWITCHING_ALLOWED = 1 << 8
    """Switching between one and three phases is allowed while plugged in."""

    RELAY2_PRESENCE_KNOWN = 1 << 9
    """``RELAY2_PRESENT`` is valid."""

    RELAY2_PRESENT = 1 << 10
    RELAY2_EXTERNAL = 1 << 11
    """Relay 2 is controlled through register 8088."""


class S0Phases(IntFlag):
    """The phases an S0 meter spreads its power over, register 8044."""

    L1 = 1 << 0
    L2 = 1 << 1
    L3 = 1 << 2
