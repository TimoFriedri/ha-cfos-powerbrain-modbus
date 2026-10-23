"""The top-level device objects of the Power Brain controller's own units."""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING, override

from modbus_connection.model import Device, Raw, UpdateReport, read_optional

from .const import WAKE_UP_SECONDS
from .enums import PhaseRelay
from .evse import EvseHealth, EvseMeter, EvseSettings, EvseStatus
from .identity import Identity
from .s0_meter import S0MeterReadings, S0MeterSettings

if TYPE_CHECKING:
    from modbus_connection import ModbusUnit


class UnsupportedDeviceError(Exception):
    """The unit answers, but does not identify as a cFos device."""


class CfosDevice(Device):
    """A cFos Modbus unit, polled as readings and settings."""

    IDENTITY: tuple[str, ...] = ()
    """Components read once at setup; part of the raw dump, never polled."""

    READINGS: tuple[str, ...] = ()
    SETTINGS: tuple[str, ...] = ()

    @property
    def serial_number(self) -> str | None:
        """Serial number of the device."""
        raise NotImplementedError

    @property
    def firmware_version(self) -> str | None:
        """Firmware version of the device."""
        raise NotImplementedError

    @property
    def private_registers(self) -> Iterable[int]:
        """Registers that identify the owner, for redacting a raw dump."""
        return ()

    async def async_update_readings(self) -> UpdateReport:
        """Refresh what the device measures."""
        return await self.async_poll(self.READINGS)

    async def async_update_settings(self) -> UpdateReport:
        """Refresh what the device is configured to do."""
        return await self.async_poll(self.SETTINGS)

    async def async_update(self) -> UpdateReport:
        """Refresh every component."""
        report = await self.async_poll(self.READINGS)
        return await self.async_poll(self.SETTINGS, report)

    @override
    async def async_read_raw(self, names: Iterable[str] | None = None) -> Raw:
        """Every register this device reads, undecoded, for diagnostics."""
        if names is None:
            names = (*self.IDENTITY, *self.READINGS, *self.SETTINGS)
        return await super().async_read_raw(names)


class PowerBrainUnit(CfosDevice):
    """A unit of the Power Brain controller; every one serves the identity block."""

    IDENTITY = ("identity",)

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        self.identity = Identity(unit)

    @property
    @override
    def serial_number(self) -> str | None:
        """Serial number of the controller."""
        return self.identity.serial_number

    @property
    @override
    def firmware_version(self) -> str | None:
        """Product version of the controller."""
        return self.identity.firmware_version

    @property
    @override
    def private_registers(self) -> Iterable[int]:
        """The serial number and the last RFID tag."""
        return (*range(8008, 8016), *range(8096, 8111))

    @override
    async def _async_setup(self) -> None:
        """Read the identity and refuse a device that is not a cFos one."""
        await self.identity.async_update()
        if not self.identity.is_cfos:
            raise UnsupportedDeviceError(
                "Unit does not report the cFos vendor id in registers 8000-8001"
            )


class CfosWallbox(PowerBrainUnit):
    """The charging station unit (default slave id 1, TCP port 4701)."""

    READINGS = ("status", "meter")
    SETTINGS = ("settings", "health")

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        self.status = EvseStatus(unit)
        self.settings = EvseSettings(unit)

        # Filled in by setup when this wallbox has them.
        self.meter: EvseMeter | None = None
        self.health: EvseHealth | None = None

    @override
    async def _async_setup(self) -> None:
        """Identify the wallbox and settle which optional blocks it serves."""
        await super()._async_setup()
        await self.status.async_update()
        if self.status.has_meter:
            self.meter = EvseMeter(self.modbus_unit)
        self.health = await read_optional(EvseHealth(self.modbus_unit))

    async def async_set_phase_relay(self, relay: PhaseRelay) -> None:
        """Charge on one or three phases (volatile)."""
        await self.status.write("phase_relay", relay)

    async def async_wake_up(self, seconds: int = WAKE_UP_SECONDS) -> None:
        """Disconnect the control pilot briefly, which wakes a sleeping vehicle."""
        await self.status.write("cp_disconnect_remaining", seconds)


class CfosS0Meter(PowerBrainUnit):
    """An S0 meter input (default slave id 2 or 3, TCP port 4702 or 4703)."""

    READINGS = ("readings",)
    SETTINGS = ("settings",)

    _RESET_PULSES = 8070
    _RESET_ENERGY = 8071

    def __init__(self, unit: ModbusUnit) -> None:
        super().__init__(unit)
        self.readings = S0MeterReadings(unit)
        self.settings = S0MeterSettings(unit)

    async def async_reset_pulses(self) -> None:
        """Zero the pulse counter (stored in flash)."""
        await self.modbus_unit.write_register(self._RESET_PULSES, 1)

    async def async_reset_energy(self) -> None:
        """Zero the energy counter (stored in flash)."""
        await self.modbus_unit.write_register(self._RESET_ENERGY, 1)
