"""An S0 meter input's register blocks."""

from __future__ import annotations

from modbus_connection.model import (
    Component,
    flags,
    int32,
    integer,
    raw_register,
    uint32,
    uint64,
)

from .enums import S0Phases
from .validators import in_range


class S0MeterReadings(Component):
    """What the S0 input has counted, registers 8050-8069."""

    register_ranges = ((8050, 8069),)

    pulses = uint64(8050)
    """Pulses counted on the input."""

    time_per_pulse = uint32(8054, unit="ms")
    """Time between the last two pulses."""

    _level = raw_register(8056)

    meter_flags = raw_register(8057)

    energy = uint64(8058, unit="Wh")
    """Imported energy."""

    power = int32(8062, unit="W")
    """Power calculated from the pulse rate."""

    current_l1 = int32(8064, scale=0.1, unit="A")
    current_l2 = int32(8066, scale=0.1, unit="A")
    current_l3 = int32(8068, scale=0.1, unit="A")

    @property
    def current_flowing(self) -> bool | None:
        """Whether current flows through the S0 input (level 0)."""
        level = self._level
        return None if level is None else level == 0

    @property
    def has_phase_currents(self) -> bool:
        """Whether currents are calculated for each phase."""
        return bool((self.meter_flags or 0) & 1)


class S0MeterSettings(Component):
    """How the S0 input turns pulses into energy, registers 8042-8047.

    Writes go to flash: change these rarely.
    """

    register_ranges = ((8042, 8047),)

    pulses_per_kwh = uint32(8042, writable=in_range(1, 100_000))
    """Pulses the connected meter emits per kWh."""

    phases = flags(8044, S0Phases, writable=True)
    """Phases the calculated power is spread over."""

    nominal_voltage_l1 = integer(
        8045, signed=False, writable=in_range(100, 280), unit="V"
    )
    nominal_voltage_l2 = integer(
        8046, signed=False, writable=in_range(100, 280), unit="V"
    )
    nominal_voltage_l3 = integer(
        8047, signed=False, writable=in_range(100, 280), unit="V"
    )
