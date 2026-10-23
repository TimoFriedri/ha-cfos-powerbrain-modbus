"""Diagnostics download and restoring state across a restart."""

from __future__ import annotations

from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    mock_restore_cache_with_extra_data,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.core import HomeAssistant, State

from tests.registers import SERIAL


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
) -> None:
    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert result["entry"]["data"]["host"] == "**REDACTED**"
    wallbox = result["wallbox"]
    assert wallbox["firmware"] == "1.25.3"
    assert wallbox["readings"]["updated"] == ["meter", "status"]
    registers = wallbox["registers"]["holding"]
    assert registers["8001"] == 0xCF05
    assert registers["8092"] == 2
    # Serial number and RFID tag are personal.
    assert registers["8008"] == "**REDACTED**"
    assert registers["8096"] == "**REDACTED**"
    assert SERIAL not in str(result)


async def test_diagnostics_without_an_answer(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    """A wallbox that stops answering still gives diagnostics, with the error."""
    mock_modbus[4701].for_unit(1).fail_requests(ModbusTimeoutError("no answer"))

    result = await get_diagnostics_for_config_entry(hass, hass_client, init_integration)

    assert "no answer" in result["wallbox"]["registers"]["error"]


async def test_session_energy_survives_restart(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    # Before the restart, 2 kWh had been charged into the vehicle still plugged in.
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.cfos_power_brain_wallbox_session_energy", "1.9"),
                {
                    "native_value": 1.9,
                    "start_energy": 1_234_567 - 2000,
                    "vehicle_connected": True,
                },
            )
        ],
    )
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.cfos_power_brain_wallbox_session_energy").state == "2.0"
    )
