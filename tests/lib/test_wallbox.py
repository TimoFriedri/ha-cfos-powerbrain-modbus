"""The charging station unit, against the in-memory mock backend."""

from __future__ import annotations

from modbus_connection import IllegalDataAddressError
from modbus_connection.mock import MockModbusUnit, WriteEvent
import pytest

from custom_components.cfos_powerbrain.cfos_modbus import (
    CfosWallbox,
    ChargePilotState,
    PhaseRelay,
    S0Inputs,
    UnsupportedDeviceError,
)
from tests.registers import SERIAL, wallbox, words

# Addresses the register map documents for the EVSE unit.
DOCUMENTED = (
    set(range(8000, 8041))
    | set(range(8057, 8070))
    | set(range(8080, 8089))
    | set(range(8090, 8114))
    | set(range(8120, 8123))
)


@pytest.fixture
def unit(mock_modbus_unit: MockModbusUnit) -> MockModbusUnit:
    mock_modbus_unit.holding.update(wallbox())
    return mock_modbus_unit


def record_writes(unit: MockModbusUnit) -> list[WriteEvent]:
    writes: list[WriteEvent] = []
    unit.on_write(writes.append)
    return writes


async def test_update_decodes_every_block(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    report = await device.async_update()

    assert report.updated == {"status", "meter", "settings", "health"}
    assert not report.failed

    assert device.identity.is_cfos
    assert device.serial_number == SERIAL
    assert device.identity.name == "cFos Power Brain Controller"
    assert device.identity.firmware_version == "1.25.3"
    assert device.identity.mapping_version == "1.2"

    status = device.status
    assert status.charge_pilot_state is ChargePilotState.CHARGING
    assert status.vehicle_connected is True
    assert status.charging is True
    assert status.problem is False
    assert status.charging_current_limit == 16.0
    assert status.charging_enabled is True
    assert status.charging_current == 16.0
    assert status.cable_current == 32.0
    assert status.phase_relay is PhaseRelay.THREE_PHASE
    assert status.last_rfid == "04A1B2C3D4"
    assert status.phase_switching_allowed
    assert not status.has_relay2

    assert device.meter is not None
    assert device.meter.energy == 1_234_567
    assert device.meter.power == 7360
    assert device.meter.current_l1 == 10.7
    assert device.meter.has_phase_currents
    assert device.meter.active_phases == 3

    assert device.settings.default_charging_current_limit == 16.0
    assert device.settings.default_charging_enabled is True
    assert device.settings.fail_safe_duration == 300
    assert device.settings.fail_safe_current == 6.0

    assert device.health is not None
    assert device.health.restart_count == 12
    assert device.health.temperature == 35


async def test_reads_stay_within_documented_registers(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    await device.async_update()

    for event in unit.read_events:
        read = set(range(event.address, event.address + event.count))
        assert read <= DOCUMENTED, f"read of undocumented {sorted(read - DOCUMENTED)}"


async def test_wallbox_without_meter_skips_meter_block(
    unit: MockModbusUnit,
) -> None:
    unit.holding.update(wallbox(has_meter=False))
    device = CfosWallbox(unit)
    report = await device.async_update()

    assert device.meter is None
    assert "meter" not in report.updated
    assert all(event.address != 8057 for event in unit.read_events)


async def test_controller_without_temperature(unit: MockModbusUnit) -> None:
    unit.fail_read(8120, IllegalDataAddressError())
    device = CfosWallbox(unit)
    report = await device.async_update()

    assert device.health is None
    assert report.updated == {"status", "meter", "settings"}


async def test_other_vendor_is_refused(unit: MockModbusUnit) -> None:
    unit.holding[8000] = [0, 0x1234]
    device = CfosWallbox(unit)

    with pytest.raises(UnsupportedDeviceError):
        await device.async_update()


async def test_vendor_id_in_either_word_order(unit: MockModbusUnit) -> None:
    unit.holding[8000] = [0xCF05, 0]
    device = CfosWallbox(unit)
    await device.async_update()

    assert device.identity.is_cfos


@pytest.mark.parametrize(
    ("raw", "state"),
    [
        (0, ChargePilotState.WAITING),
        (1, ChargePilotState.VEHICLE_DETECTED),
        (3, ChargePilotState.CHARGING_VENTILATION),
        (4, ChargePilotState.NO_POWER),
        (9, ChargePilotState.DC_SENSOR_ERROR),
        (7, ChargePilotState.ERROR),  # every undocumented code is an error
    ],
)
async def test_charge_pilot_state(
    unit: MockModbusUnit, raw: int, state: ChargePilotState
) -> None:
    unit.holding[8092] = raw
    device = CfosWallbox(unit)
    await device.async_update_readings()

    assert device.status.charge_pilot_state is state


async def test_meter_energy_of_zero_is_unknown(unit: MockModbusUnit) -> None:
    unit.holding[8058] = words(0, 4)
    device = CfosWallbox(unit)
    await device.async_update_readings()

    assert device.meter is not None
    assert device.meter.energy is None


async def test_negative_meter_power(unit: MockModbusUnit) -> None:
    unit.holding[8062] = words(-3, 2)
    device = CfosWallbox(unit)
    await device.async_update_readings()

    assert device.meter is not None
    assert device.meter.power == -3


async def test_relay2_needs_presence_bits(unit: MockModbusUnit) -> None:
    unit.holding[8113] = int(S0Inputs.RELAY2_PRESENT)
    device = CfosWallbox(unit)
    await device.async_update_readings()
    assert not device.status.has_relay2

    unit.holding[8113] = int(S0Inputs.RELAY2_PRESENT | S0Inputs.RELAY2_PRESENCE_KNOWN)
    await device.async_update_readings()
    assert device.status.has_relay2


async def test_write_charging_current_limit(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    writes = record_writes(unit)

    await device.async_set_charging_current_limit(10.7)

    assert writes == [WriteEvent("holding", 8093, [107], 0x06)]


@pytest.mark.parametrize("amps", [5.9, 63.1, 0])
async def test_charging_current_limit_out_of_range(
    unit: MockModbusUnit, amps: float
) -> None:
    device = CfosWallbox(unit)
    writes = record_writes(unit)

    with pytest.raises(ValueError):
        await device.async_set_charging_current_limit(amps)
    assert writes == []


async def test_write_volatile_controls(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    writes = record_writes(unit)

    await device.async_set_charging_enabled(False)
    await device.async_set_phase_relay(PhaseRelay.SINGLE_PHASE)
    await device.async_wake_up()
    await device.status.write("relay2", True)

    assert [(w.address, w.values) for w in writes] == [
        (8094, [0]),
        (8087, [1]),
        (8086, [5]),
        (8088, [1]),
    ]


async def test_write_fail_safe(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    writes = record_writes(unit)

    await device.settings.write("fail_safe_duration", 600)
    await device.settings.write("fail_safe_current", 0)

    assert [(w.address, w.values) for w in writes] == [
        (8083, [0, 600]),
        (8085, [0]),
    ]


async def test_raw_dump_covers_identity(unit: MockModbusUnit) -> None:
    device = CfosWallbox(unit)
    raw = await device.async_read_raw()

    assert raw["holding"][8001] == 0xCF05
    assert raw["holding"][8092] == 2
    assert 8058 in raw["holding"]
