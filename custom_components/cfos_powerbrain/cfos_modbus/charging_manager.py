"""The Charging Manager's SunSpec Modbus server.

The Charging Manager built into the Power Brain is reached separately from the
controller's own units. Once its SunSpec server is switched on under "SunSpec
address settings" in the Charging Manager configuration, it answers on the TCP
port and Modbus ID set there. Its values sit in SunSpec models from register
40000 on: the common model, seven meter models, then the custom models 60000
(parameters), 60001 (flags) and 60002 (variables). cFos may add values to the
models, so the addresses are discovered by scanning the model chain.
"""

from __future__ import annotations

from typing import TYPE_CHECKING, Final

from modbus_connection.model import Component, float32 as scaled_float32
from modbus_connection.model.sunspec import (
    SunSpecComponent,
    SunSpecError,
    boolean,
    float32,
    model_length_group,
    scan,
    string,
)

from .device import CfosDevice, UnsupportedDeviceError
from .validators import in_range

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit
    from modbus_connection.model.sunspec import SunSpecModel, SunSpecModels

SUNSPEC_BASE_ADDRESS: Final = 40000
DEFAULT_CHARGING_MANAGER_PORT: Final = 502
DEFAULT_CHARGING_MANAGER_UNIT_ID: Final = 1

COMMON_MODEL: Final = 1
METER_MODEL: Final = 213
PARAMETERS_MODEL: Final = 60000
FLAGS_MODEL: Final = 60001
VARIABLES_MODEL: Final = 60002

METERS: Final = (
    "grid",
    "consumers",
    "generators",
    "pv_surplus",
    "wallbox_used",
    "wallbox_available",
    "fault",
)
"""The meter models after the common model, in chain order: grid consumption,
total consumers, total generators, PV surplus, utilised wallbox power,
available wallbox power and fault power."""

_MAX_CURRENT: Final = 1000.0
"""Highest current accepted for a Charging Manager parameter, in A."""


class CmCommon(SunSpecComponent):
    """SunSpec model 1: who the Charging Manager is."""

    manufacturer = string(2, 16)
    model = string(18, 16)
    version = string(42, 8)
    serial_number = string(50, 16)


class CmMeter(SunSpecComponent):
    """SunSpec model 213: one of the Charging Manager's meter values."""

    # One read for the block in use rather than two around the unused points.
    register_ranges = ((0, 69),)

    current = float32(2, unit="A")
    """Total of the phase currents."""

    current_l1 = float32(4, unit="A")
    current_l2 = float32(6, unit="A")
    current_l3 = float32(8, unit="A")

    voltage_l1 = float32(12, unit="V")
    voltage_l2 = float32(14, unit="V")
    voltage_l3 = float32(16, unit="V")

    frequency = float32(26, unit="Hz")

    power = float32(28, unit="W")
    """Active power; for the grid meter this is register 40098 on current firmware."""

    power_l1 = float32(30, unit="W")
    power_l2 = float32(32, unit="W")
    power_l3 = float32(34, unit="W")

    energy_exported = float32(60, unit="Wh")
    energy_imported = float32(68, unit="Wh")


class CmParameters(SunSpecComponent):
    """Model 60000: the global Charging Manager parameters.

    The Charging Manager saves these to flash within 150 s of a change: set
    them rarely. The registers hold mA; the fields read and write A.
    """

    max_total_current = scaled_float32(
        2, scale=0.001, writable=in_range(0, _MAX_CURRENT), unit="A"
    )
    """Maximum total current of the installation, per phase."""

    power_reserve = scaled_float32(
        4, scale=0.001, writable=in_range(0, _MAX_CURRENT), unit="A"
    )
    """Current kept in reserve."""

    overdraw = scaled_float32(
        6, scale=0.001, writable=in_range(0, _MAX_CURRENT), unit="A"
    )
    """Current the installation may briefly exceed its maximum by."""

    max_wallbox_current = scaled_float32(
        8, scale=0.001, writable=in_range(0, _MAX_CURRENT), unit="A"
    )
    """Maximum total current of all wallboxes, per phase."""

    max_phase_imbalance = scaled_float32(
        10, scale=0.001, writable=in_range(0, _MAX_CURRENT), unit="A"
    )
    """Maximum imbalance between the phases."""

    load_management = float32(12, writable=in_range(0, 1))
    """1 while load management is active, 0 while not."""

    imbalance_includes_consumers = float32(14, writable=in_range(0, 1))
    """1 if the home consumption counts toward the phase imbalance."""


class CmLimit(SunSpecComponent):
    """Model 60000, offset 16: the maximum total current in percent.

    Unlike the rest of model 60000 it is not saved, so it may be written as
    often as needed, e.g. to follow a grid operator's request. Register 40968
    on current firmware.
    """

    max_total_current_percent = float32(16, writable=in_range(0, 100), unit="%")


class CmFlag(Component):
    """One Charging Manager flag, ``CM._flagN`` in formulas."""

    on = boolean(2, writable=True)


class CmFlags(SunSpecComponent):
    """Model 60001: 32 flags for formulas. Not saved; write as often as needed."""

    flags = model_length_group(CmFlag, start=2, stride=1)


class CmVariable(Component):
    """A Charging Manager variable: a 20-register name and a float value."""

    name = string(2, 20)
    value = float32(22, writable=True)


class CmVariableLongName(Component):
    """A Charging Manager variable with a 21-register name."""

    name = string(2, 21)
    value = float32(23, writable=True)


class CmVariables(SunSpecComponent):
    """Model 60002: the Charging Manager variables, 22 registers each.

    The values are not saved and may be written as often as needed. Writing a
    value replaces a formula the variable had with that fixed value.
    """

    variables = model_length_group(CmVariable, start=2, stride=22)


class CmVariablesLongName(SunSpecComponent):
    """Model 60002 in the layout of the register table: 23 registers each."""

    variables = model_length_group(CmVariableLongName, start=2, stride=23)


def _is_name(words: list[int]) -> bool:
    """Whether registers hold a non-empty, printable, NUL-padded ASCII name."""
    raw = b"".join(word.to_bytes(2, "big") for word in words)
    text = raw.rstrip(b"\0")
    return bool(text) and all(0x20 <= byte < 0x7F for byte in text)


async def _async_read_model(unit: ModbusUnit, model: SunSpecModel) -> list[int]:
    """Read a model's data registers, in requests of at most 125."""
    words: list[int] = []
    for start in range(0, model.length, 125):
        count = min(125, model.length - start)
        words += await unit.read_holding_registers(model.address + 2 + start, count)
    return words


async def _async_variables(
    unit: ModbusUnit, model: SunSpecModel
) -> CmVariables | CmVariablesLongName | None:
    """Place the variables, in whichever layout the model's contents fit.

    The cFos documentation describes 22 registers per variable in its text and
    23 in its register table. Pick the layout that divides the model and
    whose every name reads as text; None if neither fits.
    """
    if model.length == 0:
        return None
    words = await _async_read_model(unit, model)
    for stride, component in ((22, CmVariables), (23, CmVariablesLongName)):
        if model.length % stride:
            continue
        name_length = stride - 2
        if all(
            _is_name(words[start : start + name_length])
            for start in range(0, model.length, stride)
        ):
            return component(unit, model)
    return None


class CfosChargingManager(CfosDevice):
    """The Charging Manager, through its SunSpec server."""

    IDENTITY = ("common",)
    READINGS = (*METERS, "limit", "flags", "variables")
    SETTINGS = ("parameters",)

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        self.models: SunSpecModels | None = None

        # Filled in by setup from the discovered model chain.
        self.common: CmCommon | None = None
        self.grid: CmMeter | None = None
        self.consumers: CmMeter | None = None
        self.generators: CmMeter | None = None
        self.pv_surplus: CmMeter | None = None
        self.wallbox_used: CmMeter | None = None
        self.wallbox_available: CmMeter | None = None
        self.fault: CmMeter | None = None
        self.parameters: CmParameters | None = None
        self.limit: CmLimit | None = None
        self.flags: CmFlags | None = None
        self.variables: CmVariables | CmVariablesLongName | None = None

    @property
    def serial_number(self) -> str | None:
        """Serial number the Charging Manager reports."""
        return self.common.serial_number if self.common else None

    @property
    def firmware_version(self) -> str | None:
        """Version the Charging Manager reports."""
        return self.common.version if self.common else None

    @property
    def private_registers(self) -> range:
        """The registers of the serial number, for redacting a raw dump."""
        if self.common is None:
            return range(0)
        start = self.common.resolved_fields["serial_number"].address
        return range(start, start + 16)

    async def _async_setup(self) -> None:
        """Discover the models and place a component on each one in use."""
        unit = self.modbus_unit
        try:
            models = await scan(unit, SUNSPEC_BASE_ADDRESS)
        except SunSpecError as err:
            raise UnsupportedDeviceError(
                "No SunSpec server answers; switch it on under 'SunSpec address "
                "settings' in the Charging Manager configuration"
            ) from err
        if (common := models.first(COMMON_MODEL)) is None:
            raise UnsupportedDeviceError("The SunSpec server has no common model")
        self.common = CmCommon(unit, common)
        await self.common.async_update()

        for name, meter in zip(METERS, models.get(METER_MODEL, []), strict=False):
            setattr(self, name, CmMeter(unit, meter))
        if (parameters := models.first(PARAMETERS_MODEL)) is not None:
            if parameters.length >= 14:
                self.parameters = CmParameters(unit, parameters)
            if parameters.length >= 16:
                self.limit = CmLimit(unit, parameters)
        if (flags := models.first(FLAGS_MODEL)) is not None:
            self.flags = CmFlags(unit, flags)
        if (variables := models.first(VARIABLES_MODEL)) is not None:
            self.variables = await _async_variables(unit, variables)
        self.models = models

    @property
    def variable_names(self) -> list[str]:
        """Names of the Charging Manager variables, in model order."""
        if self.variables is None:
            return []
        return [variable.name or "" for variable in self.variables.variables]

    async def async_set_max_total_current_percent(self, percent: float) -> None:
        """Limit the total current to a share of its maximum (not saved)."""
        if self.limit is None:
            raise UnsupportedDeviceError("The Charging Manager has no current limit")
        await self.limit.write("max_total_current_percent", percent)

    async def async_set_flag(self, number: int, on: bool) -> None:
        """Set flag ``number`` (1-32), ``CM._flagN`` in formulas (not saved)."""
        if self.flags is None or not 1 <= number <= len(self.flags.flags):
            raise UnsupportedDeviceError(f"The Charging Manager has no flag {number}")
        await self.flags.flags[number - 1].write("on", on)

    async def async_set_variable(self, name: str, value: float) -> None:
        """Give a variable a fixed value, replacing its formula (not saved).

        Raises ``KeyError`` if the Charging Manager has no variable ``name``.
        """
        if self.variables is not None:
            for variable in self.variables.variables:
                if variable.name == name:
                    await variable.write("value", value)
                    return
        raise KeyError(name)
