"""The Charging Manager's SunSpec server, against the in-memory mock backend."""

from __future__ import annotations

from modbus_connection.mock import MockModbusUnit
from modbus_connection.model.sunspec import SunSpecMapShiftError
import pytest

from cfos_modbus import METERS, CfosChargingManager, UnsupportedDeviceError
from tests.registers import (
    CM_METER_POWER,
    CM_SERIAL,
    charging_manager,
    float_words,
    record_writes,
)


@pytest.fixture
def unit(mock_modbus_unit: MockModbusUnit) -> MockModbusUnit:
    mock_modbus_unit.holding.update(charging_manager())
    return mock_modbus_unit


async def test_update(unit: MockModbusUnit) -> None:
    cm = CfosChargingManager(unit)
    report = await cm.async_update()

    assert report.updated == {*METERS, "limit", "flags", "variables", "parameters"}
    assert cm.serial_number == CM_SERIAL
    assert cm.firmware_version == "2.1.4"
    assert cm.common is not None
    assert cm.common.manufacturer == "cFos"

    for name, power in CM_METER_POWER.items():
        meter = getattr(cm, name)
        assert meter is not None, name
        assert meter.power == pytest.approx(power), name
    assert cm.grid is not None
    assert cm.grid.voltage_l2 == pytest.approx(231.0)
    assert cm.grid.energy_imported == pytest.approx(250000.0)

    assert cm.parameters is not None
    assert cm.parameters.max_total_current == pytest.approx(63.0)
    assert cm.parameters.max_wallbox_current == pytest.approx(32.0)
    assert cm.parameters.load_management == 1.0
    assert cm.parameters.imbalance_includes_consumers == 0.0
    assert cm.limit is not None
    assert cm.limit.max_total_current_percent == pytest.approx(100.0)

    assert cm.flags is not None
    assert [flag.on for flag in cm.flags.flags][:4] == [False, False, True, False]
    assert len(cm.flags.flags) == 32
    assert cm.variable_names == ["pv_mode", "night_rate"]


async def test_documented_addresses(unit: MockModbusUnit) -> None:
    """On today's firmware, the grid power is 40098 and the percent 40968."""
    cm = CfosChargingManager(unit)
    await cm.async_update()

    assert cm.grid is not None
    assert cm.grid.resolved_fields["power"].address == 40098
    assert cm.limit is not None
    assert cm.limit.resolved_fields["max_total_current_percent"].address == 40968


async def test_variables_in_the_register_table_layout(
    mock_modbus_unit: MockModbusUnit,
) -> None:
    mock_modbus_unit.holding.update(charging_manager(name_registers=21))
    cm = CfosChargingManager(mock_modbus_unit)
    await cm.async_update()

    assert cm.variable_names == ["pv_mode", "night_rate"]
    assert cm.variables is not None
    assert [v.value for v in cm.variables.variables] == [1.0, 2.0]


async def test_no_variables(mock_modbus_unit: MockModbusUnit) -> None:
    mock_modbus_unit.holding.update(charging_manager(variables=()))
    cm = CfosChargingManager(mock_modbus_unit)
    await cm.async_update()

    assert cm.variables is None
    assert cm.variable_names == []


async def test_writes(unit: MockModbusUnit) -> None:
    cm = CfosChargingManager(unit)
    await cm.async_update()
    writes = record_writes(unit)

    assert cm.limit is not None
    assert cm.flags is not None
    assert cm.parameters is not None
    await cm.limit.write("max_total_current_percent", 50)
    await cm.flags.flags[2].write("on", False)
    await cm.async_set_variable("night_rate", 0.25)
    await cm.parameters.write("max_total_current", 40)

    assert writes == [
        (40968, float_words(50.0)),
        (40972 + 2, [0]),
        (41004 + 2 + 22 + 20, float_words(0.25)),
        (40954, float_words(40000.0)),
    ]


async def test_rejected_writes(unit: MockModbusUnit) -> None:
    cm = CfosChargingManager(unit)
    await cm.async_update()
    writes = record_writes(unit)

    assert cm.limit is not None
    with pytest.raises(ValueError):
        await cm.limit.write("max_total_current_percent", 101)
    with pytest.raises(KeyError):
        await cm.async_set_variable("unknown", 1)
    assert writes == []


async def test_no_sunspec_server(mock_modbus_unit: MockModbusUnit) -> None:
    cm = CfosChargingManager(mock_modbus_unit)

    with pytest.raises(UnsupportedDeviceError, match="SunSpec"):
        await cm.async_update()


async def test_model_moved(unit: MockModbusUnit) -> None:
    """A firmware update that grows a model shifts the ones behind it."""
    cm = CfosChargingManager(unit)
    await cm.async_update()

    unit.holding.update({40952: [0xFFFF, 0]})  # 60000 is gone from its place

    with pytest.raises(SunSpecMapShiftError):
        await cm.async_update_settings()


async def test_raw_dump_covers_the_common_model(unit: MockModbusUnit) -> None:
    cm = CfosChargingManager(unit)
    raw = await cm.async_read_raw()

    assert raw["holding"][40002] == 1
    assert 40098 in raw["holding"]
    assert set(cm.private_registers) == set(range(40052, 40068))  # SN, offset 50
