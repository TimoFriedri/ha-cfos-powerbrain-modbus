"""An S0 meter input, against the in-memory mock backend."""

from __future__ import annotations

from modbus_connection.mock import MockModbusUnit
import pytest

from cfos_modbus import CfosS0Meter, S0Phases
from tests.registers import record_writes, s0_meter


@pytest.fixture
def unit(mock_modbus_unit: MockModbusUnit) -> MockModbusUnit:
    mock_modbus_unit.holding.update(s0_meter())
    return mock_modbus_unit


async def test_update(unit: MockModbusUnit) -> None:
    meter = CfosS0Meter(unit)
    report = await meter.async_update()

    assert report.updated == {"readings", "settings"}
    assert meter.identity.device_id == 0x101
    assert meter.readings.energy == 5_000_000
    assert meter.readings.power == 3000
    assert meter.readings.current_l2 == 4.3
    assert meter.readings.pulses == 5_000_000
    assert meter.readings.time_per_pulse == 1200
    assert meter.readings.current_flowing is True
    assert meter.readings.has_phase_currents
    assert meter.settings.pulses_per_kwh == 1000
    assert meter.settings.phases == S0Phases.L1 | S0Phases.L2 | S0Phases.L3
    assert meter.settings.nominal_voltage_l1 == 230


async def test_s0_energy_may_be_zero(unit: MockModbusUnit) -> None:
    unit.holding[8058] = [0, 0, 0, 0]
    meter = CfosS0Meter(unit)
    await meter.async_update_readings()

    assert meter.readings.energy == 0


async def test_resets(unit: MockModbusUnit) -> None:
    meter = CfosS0Meter(unit)
    writes = record_writes(unit)

    await meter.async_reset_energy()
    await meter.async_reset_pulses()

    assert writes == [(8071, [1]), (8070, [1])]
