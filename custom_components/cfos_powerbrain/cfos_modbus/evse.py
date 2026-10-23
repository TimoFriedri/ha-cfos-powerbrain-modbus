"""The charging station (EVSE) unit's register blocks."""

from __future__ import annotations

from modbus_connection.model import (
    Component,
    NumberField,
    boolean,
    enum,
    flags,
    gauge,
    int32,
    integer,
    raw_register,
    string,
    uint32,
    uint64,
)

from .enums import ChargePilotState, PhaseRelay, S0Inputs, charge_pilot_state
from .validators import charging_current, charging_current_or_off, in_range

# Registers the map leaves undocumented sit between the blocks, so every
# component names the ranges it may read instead of bridging gaps.


class EvseStatus(Component):
    """What the charging station is doing now, registers 8086-8113.

    Every writable register here is volatile: the device does not store it in
    flash, so it may be written as often as needed. After a reboot the
    charging limit and enable flag fall back to their defaults in
    ``EvseSettings``.
    """

    register_ranges = ((8086, 8088), (8090, 8113))

    cp_disconnect_remaining = integer(
        8086, signed=False, writable=in_range(0, 300), unit="s"
    )
    """Seconds the control pilot stays disconnected; write to disconnect it."""

    phase_relay = enum(8087, PhaseRelay, writable=True)
    """The contactor in use (controller Rev. F and later)."""

    relay2 = boolean(8088, writable=True)
    """The second relay (controller Rev. F and later, only while relay 1 is off)."""

    cable_current = gauge(8090, 0.1, signed=False, unit="A")
    """Current rating of the plugged cable (proximity pilot), 0 without cable."""

    fixed_current = gauge(
        8091, 0.1, signed=False, writable=charging_current_or_off, unit="A"
    )
    """Override of the cable rating."""

    charge_pilot_state: NumberField[ChargePilotState] = NumberField(
        8092, signed=False, convert=charge_pilot_state
    )
    """Control pilot state."""

    charging_current_limit = gauge(
        8093, 0.1, signed=False, writable=charging_current, unit="A"
    )
    """The most the vehicle may draw; the model may cap it lower."""

    charging_enabled = boolean(8094, writable=True)
    """Whether charging is allowed."""

    charging_current = gauge(8095, 0.1, signed=False, unit="A")
    """The current signalled to the vehicle."""

    last_rfid = string(8096, 15)
    """The last RFID tag seen, as a hex string."""

    detected_rfids = integer(8111, signed=False)
    """Number of RFID inputs."""

    has_meter = boolean(8112)
    """Whether a meter is attached, which makes ``EvseMeter`` readable."""

    s0_inputs = flags(8113, S0Inputs)
    """S0 input levels and hardware capabilities."""

    @property
    def vehicle_connected(self) -> bool | None:
        """Whether a vehicle is plugged in."""
        state = self.charge_pilot_state
        return None if state is None else state.vehicle_connected

    @property
    def charging(self) -> bool | None:
        """Whether the vehicle is charging."""
        state = self.charge_pilot_state
        return None if state is None else state.charging

    @property
    def problem(self) -> bool | None:
        """Whether the control pilot reports a fault."""
        state = self.charge_pilot_state
        return None if state is None else state.problem

    @property
    def phase_switching_allowed(self) -> bool:
        """Whether the wallbox may switch between one and three phases."""
        inputs = self.s0_inputs
        return inputs is not None and S0Inputs.PHASE_SWITCHING_ALLOWED in inputs

    @property
    def has_relay2(self) -> bool:
        """Whether a second relay is fitted and its presence is reported."""
        inputs = self.s0_inputs
        return (
            inputs is not None
            and S0Inputs.RELAY2_PRESENCE_KNOWN in inputs
            and S0Inputs.RELAY2_PRESENT in inputs
        )


class EvseMeter(Component):
    """The meter attached to the charging station, registers 8057-8069.

    Readable only while ``EvseStatus.has_meter`` is set.
    """

    register_ranges = ((8057, 8069),)

    meter_flags = raw_register(8057)

    # Shortly after it starts, the controller reports 0 Wh until it has read
    # the meter. A real meter has counted something, so 0 reads as unknown.
    energy = uint64(8058, nan=0, unit="Wh")
    """Imported energy over the meter's lifetime."""

    power = int32(8062, unit="W")
    """Active power."""

    current_l1 = int32(8064, scale=0.1, unit="A")
    current_l2 = int32(8066, scale=0.1, unit="A")
    current_l3 = int32(8068, scale=0.1, unit="A")

    @property
    def has_phase_currents(self) -> bool:
        """Whether the meter measures each phase on its own."""
        return bool((self.meter_flags or 0) & 1)

    @property
    def active_phases(self) -> int | None:
        """How many phases carry at least 1 A."""
        currents = (self.current_l1, self.current_l2, self.current_l3)
        if any(current is None for current in currents):
            return None
        return sum(1 for current in currents if current is not None and current >= 1)


class EvseSettings(Component):
    """Power-on defaults and the Modbus fail-safe, registers 8080-8085.

    Writes go to flash: change these rarely, never from a frequent automation.
    """

    register_ranges = ((8080, 8085),)

    default_fixed_current = gauge(
        8080, 0.1, signed=False, writable=charging_current_or_off, unit="A"
    )
    """``EvseStatus.fixed_current`` after a reboot."""

    default_charging_current_limit = gauge(
        8081, 0.1, signed=False, writable=charging_current, unit="A"
    )
    """``EvseStatus.charging_current_limit`` after a reboot."""

    default_charging_enabled = boolean(8082, writable=True)
    """``EvseStatus.charging_enabled`` after a reboot."""

    fail_safe_duration = uint32(8083, writable=in_range(0, 86400), unit="s")
    """Seconds without Modbus traffic before ``fail_safe_current`` applies; 0 disables."""

    fail_safe_current = gauge(
        8085, 0.1, signed=False, writable=charging_current_or_off, unit="A"
    )
    """Current allowed while Modbus is silent; 0 stops charging."""


class EvseHealth(Component):
    """Restart counter and controller temperature, registers 8120-8122.

    The temperature needs controller Rev. 3.0 or a cFos Wallbox Booster.
    """

    register_ranges = ((8120, 8122),)

    restart_count = uint32(8120)
    """Number of hardware restarts."""

    temperature = integer(8122, unit="°C")
    """Controller temperature."""
