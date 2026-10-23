"""The config, reconfigure and options flows."""

from __future__ import annotations

from collections.abc import Callable
from unittest.mock import patch

from modbus_connection import ModbusConnectionError, ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.config_entries import SOURCE_USER
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType, InvalidData

from custom_components.cfos_powerbrain.const import (
    CONF_CHARGING_MANAGER,
    CONF_CHARGING_MANAGER_PORT,
    CONF_CHARGING_MANAGER_UNIT_ID,
    CONF_S0_METERS,
    DOMAIN,
)
from tests.integration.conftest import ENTRY_DATA, ReopenableMockConnection
from tests.registers import SERIAL, ascii_words


async def test_user_flow(
    hass: HomeAssistant, mock_modbus: dict[int, MockModbusConnection]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "user"

    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_SCAN_INTERVAL: 5}
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["title"] == "cFos Power Brain Wallbox"
    assert result["data"] == ENTRY_DATA
    assert result["options"] == {
        CONF_SCAN_INTERVAL: 5,
        # The Charging Manager stays off unless switched on.
        CONF_CHARGING_MANAGER: False,
        CONF_CHARGING_MANAGER_PORT: 502,
        CONF_CHARGING_MANAGER_UNIT_ID: 1,
    }
    assert result["result"].unique_id == SERIAL


async def test_user_flow_default_scan_interval(
    hass: HomeAssistant, mock_modbus: dict[int, MockModbusConnection]
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["options"][CONF_SCAN_INTERVAL] == 10


@pytest.mark.parametrize("seconds", [0, 31])
async def test_user_flow_rejects_scan_interval_out_of_range(
    hass: HomeAssistant, mock_modbus: dict[int, MockModbusConnection], seconds: int
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    with pytest.raises(InvalidData):
        await hass.config_entries.flow.async_configure(
            result["flow_id"], {**ENTRY_DATA, CONF_SCAN_INTERVAL: seconds}
        )


def _no_answer(unit: MockModbusUnit) -> Callable[[], None]:
    unit.fail_requests(ModbusTimeoutError("no answer"))
    return lambda: unit.fail_requests(None)


def _other_vendor(unit: MockModbusUnit) -> Callable[[], None]:
    unit.holding[8000] = [0, 0x1234]
    return lambda: unit.holding.update({8000: [0, 0xCF05]})


def _no_serial(unit: MockModbusUnit) -> Callable[[], None]:
    unit.holding[8008] = [0] * 8
    return lambda: unit.holding.update({8008: ascii_words(SERIAL, 8)})


def _unexpected(unit: MockModbusUnit) -> Callable[[], None]:
    failing = patch(
        "custom_components.cfos_powerbrain.config_flow.CfosWallbox.async_ensure_setup",
        side_effect=RuntimeError("boom"),
    )
    failing.start()
    return failing.stop


@pytest.mark.parametrize(
    ("cause", "error"),
    [
        (_no_answer, "cannot_connect"),
        (_other_vendor, "not_cfos"),
        (_no_serial, "not_cfos"),
        (_unexpected, "unknown"),
    ],
)
async def test_user_flow_recovers_from_error(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    cause: Callable[[MockModbusUnit], Callable[[], None]],
    error: str,
) -> None:
    undo = cause(mock_modbus[4701].for_unit(1))
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    undo()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].unique_id == SERIAL


async def test_user_flow_already_configured(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    config_entry.add_to_hass(hass)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "already_configured"


async def test_reconfigure_flow(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    # The wallbox moved to a new address; same controller behind it.
    result = await init_integration.start_reconfigure_flow(hass)
    assert result["type"] is FlowResultType.FORM
    assert result["step_id"] == "reconfigure"

    new_data = {**ENTRY_DATA, CONF_HOST: "192.168.1.51"}
    result = await hass.config_entries.flow.async_configure(result["flow_id"], new_data)
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
    assert init_integration.data[CONF_HOST] == "192.168.1.51"


async def test_reconfigure_flow_wrong_device(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    other = ReopenableMockConnection()
    other.for_unit(1).holding.update(mock_modbus[4701].for_unit(1).holding)
    other.for_unit(1).holding[8008] = [0x5858] * 8  # serial "XXXXXXXXXXXXXXXX"
    mock_modbus[4801] = other

    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, CONF_PORT: 4801}
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "wrong_device"
    assert init_integration.data == ENTRY_DATA


async def test_options_flow(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    assert result["type"] is FlowResultType.FORM

    result = await hass.config_entries.options.async_configure(
        result["flow_id"], {CONF_SCAN_INTERVAL: 5, CONF_S0_METERS: ["1"]}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.options == {
        CONF_SCAN_INTERVAL: 5,
        CONF_S0_METERS: ["1"],
        # The Charging Manager stays off unless switched on.
        CONF_CHARGING_MANAGER: False,
        CONF_CHARGING_MANAGER_PORT: 502,
        CONF_CHARGING_MANAGER_UNIT_ID: 1,
    }
    # The entry reloaded with the S0 meter.
    assert 1 in init_integration.runtime_data.s0_meters


async def test_options_flow_rejects_scan_interval_out_of_range(
    hass: HomeAssistant, init_integration: MockConfigEntry
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    with pytest.raises(InvalidData):
        await hass.config_entries.options.async_configure(
            result["flow_id"], {CONF_SCAN_INTERVAL: 31, CONF_S0_METERS: []}
        )


async def test_reconfigure_flow_recovers_from_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    unit = mock_modbus[4701].for_unit(1)
    unit.fail_requests(ModbusConnectionError("refused"))
    result = await init_integration.start_reconfigure_flow(hass)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "cannot_connect"}

    unit.fail_requests(None)
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], ENTRY_DATA
    )
    assert result["type"] is FlowResultType.ABORT
    assert result["reason"] == "reconfigure_successful"
