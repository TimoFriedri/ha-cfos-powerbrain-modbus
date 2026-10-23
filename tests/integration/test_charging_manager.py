"""The Charging Manager as its own device, through its SunSpec server."""

from __future__ import annotations

from collections.abc import Callable
from datetime import timedelta
from typing import Any
from unittest.mock import patch

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import ModbusConnectionError
from modbus_connection.mock import MockModbusConnection, MockModbusUnit, WriteEvent
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)
from pytest_homeassistant_custom_component.components.diagnostics import (
    get_diagnostics_for_config_entry,
)
from pytest_homeassistant_custom_component.typing import ClientSessionGenerator

from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.config_entries import SOURCE_USER, ConfigEntryState
from homeassistant.const import (
    ATTR_ENTITY_ID,
    CONF_SCAN_INTERVAL,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
    STATE_UNAVAILABLE,
)
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResultType
from homeassistant.exceptions import ServiceValidationError
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.cfos_powerbrain.const import (
    CONF_CHARGING_MANAGER,
    CONF_CHARGING_MANAGER_PORT,
    CONF_CHARGING_MANAGER_UNIT_ID,
    CONF_S0_METERS,
    DOMAIN,
)
from tests.integration.conftest import ENTRY_DATA
from tests.registers import CM_SERIAL, SERIAL, charging_manager, float_words

MANAGER_OPTIONS = {
    CONF_CHARGING_MANAGER: True,
    CONF_CHARGING_MANAGER_PORT: 502,
    CONF_CHARGING_MANAGER_UNIT_ID: 1,
}


@pytest.fixture
def manager_unit(mock_modbus: dict[int, MockModbusConnection]) -> MockModbusUnit:
    return mock_modbus[502].for_unit(1)


@pytest.fixture
async def init_with_manager(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> MockConfigEntry:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options=MANAGER_OPTIONS)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry


def record_writes(unit: MockModbusUnit) -> list[tuple[int, list[int]]]:
    writes: list[tuple[int, list[int]]] = []

    def record(event: WriteEvent) -> None:
        writes.append((event.address, [int(value) for value in event.values]))

    unit.on_write(record)
    return writes


async def poll(hass: HomeAssistant, freezer: FrozenDateTimeFactory) -> None:
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()


async def test_enable_in_options(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    device_registry: dr.DeviceRegistry,
) -> None:
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"],
        {CONF_SCAN_INTERVAL: 10, CONF_S0_METERS: [], **MANAGER_OPTIONS},
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY

    manager = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{SERIAL}_charging_manager"), init_integration.entry_id
    )
    assert manager is not None
    assert manager.name == "cFos Charging Manager"
    assert manager.model == "Charging Manager"
    assert manager.sw_version == "2.1.4"
    # Next to the charging point, not behind it.
    assert manager.via_device_id is None
    assert (
        float(hass.states.get("sensor.cfos_charging_manager_grid_power").state) == 2500
    )


async def test_enable_during_setup(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    device_registry: dr.DeviceRegistry,
) -> None:
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], {**ENTRY_DATA, **MANAGER_OPTIONS}
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["data"] == ENTRY_DATA
    assert result["options"] == {CONF_SCAN_INTERVAL: 10, **MANAGER_OPTIONS}

    entry = result["result"]
    assert entry.runtime_data.charging_manager is not None
    assert device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{SERIAL}_charging_manager"), entry.entry_id
    )
    assert (
        float(hass.states.get("sensor.cfos_charging_manager_grid_power").state) == 2500
    )


def _wrong_modbus_id(
    options: dict[str, Any], unit: MockModbusUnit
) -> Callable[[], None]:
    options[CONF_CHARGING_MANAGER_UNIT_ID] = 9  # nothing answers there
    return lambda: None  # the retry sends the right Modbus ID


def _refused(options: dict[str, Any], unit: MockModbusUnit) -> Callable[[], None]:
    unit.fail_requests(ModbusConnectionError("refused"))
    return lambda: unit.fail_requests(None)


def _unexpected(options: dict[str, Any], unit: MockModbusUnit) -> Callable[[], None]:
    failing = patch(
        "custom_components.cfos_powerbrain.config_flow.CfosChargingManager.async_ensure_setup",
        side_effect=RuntimeError("boom"),
    )
    failing.start()
    return failing.stop


PROBE_ERRORS = pytest.mark.parametrize(
    ("cause", "error"),
    [
        (_wrong_modbus_id, "charging_manager_not_found"),
        (_refused, "charging_manager_cannot_connect"),
        (_unexpected, "unknown"),
    ],
)


@PROBE_ERRORS
async def test_enable_during_setup_recovers_from_error(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    manager_unit: MockModbusUnit,
    cause: Callable[[dict[str, Any], MockModbusUnit], Callable[[], None]],
    error: str,
) -> None:
    user_input: dict[str, Any] = {**ENTRY_DATA, **MANAGER_OPTIONS}
    broken = dict(user_input)
    undo = cause(broken, manager_unit)
    result = await hass.config_entries.flow.async_init(
        DOMAIN, context={"source": SOURCE_USER}
    )
    result = await hass.config_entries.flow.async_configure(result["flow_id"], broken)
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    undo()
    result = await hass.config_entries.flow.async_configure(
        result["flow_id"], user_input
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert result["result"].runtime_data.charging_manager is not None


@PROBE_ERRORS
async def test_enable_in_options_recovers_from_error(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    manager_unit: MockModbusUnit,
    cause: Callable[[dict[str, Any], MockModbusUnit], Callable[[], None]],
    error: str,
) -> None:
    options: dict[str, Any] = {
        CONF_SCAN_INTERVAL: 10,
        CONF_S0_METERS: [],
        **MANAGER_OPTIONS,
    }
    broken = dict(options)
    undo = cause(broken, manager_unit)
    result = await hass.config_entries.options.async_init(init_integration.entry_id)
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], broken
    )
    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": error}

    undo()
    result = await hass.config_entries.options.async_configure(
        result["flow_id"], options
    )
    await hass.async_block_till_done()
    assert result["type"] is FlowResultType.CREATE_ENTRY
    assert init_integration.runtime_data.charging_manager is not None


@pytest.mark.usefixtures("init_with_manager")
async def test_states(hass: HomeAssistant) -> None:
    expected = {
        "sensor.cfos_charging_manager_grid_power": 2500,
        "sensor.cfos_charging_manager_consumers_power": 9800,
        "sensor.cfos_charging_manager_generators_power": 7300,
        "sensor.cfos_charging_manager_pv_surplus": 0,
        "sensor.cfos_charging_manager_wallbox_power_used": 7360,
        "sensor.cfos_charging_manager_wallbox_power_available": 11040,
        "sensor.cfos_charging_manager_fault_power": 0,
        "sensor.cfos_charging_manager_variable_pv_mode": 1,
        "sensor.cfos_charging_manager_variable_night_rate": 2,
        "number.cfos_charging_manager_total_current_limit": 100,
    }
    for entity_id, value in expected.items():
        assert (current := hass.states.get(entity_id)) is not None, entity_id
        assert float(current.state) == pytest.approx(value), entity_id

    # Flags and the flash-backed parameters wait to be enabled.
    assert hass.states.get("switch.cfos_charging_manager_flag_3") is None
    assert hass.states.get("number.cfos_charging_manager_maximum_total_current") is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_with_manager")
async def test_hidden_entities(hass: HomeAssistant) -> None:
    expected = {
        "switch.cfos_charging_manager_flag_3": STATE_ON,
        "switch.cfos_charging_manager_flag_4": STATE_OFF,
        "switch.cfos_charging_manager_load_management": STATE_ON,
        "switch.cfos_charging_manager_imbalance_includes_consumers": STATE_OFF,
        "number.cfos_charging_manager_maximum_total_current": "63.0",
        "number.cfos_charging_manager_maximum_wallbox_current": "32.0",
        "sensor.cfos_charging_manager_grid_energy_imported": "250.0",
    }
    for entity_id, state in expected.items():
        assert (current := hass.states.get(entity_id)) is not None, entity_id
        assert current.state == state, entity_id
    current_l2 = hass.states.get("sensor.cfos_charging_manager_grid_current_l2")
    assert float(current_l2.state) == pytest.approx(2500 / 230 / 3)


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_with_manager")
async def test_writes(hass: HomeAssistant, manager_unit: MockModbusUnit) -> None:
    writes = record_writes(manager_unit)

    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.cfos_charging_manager_total_current_limit",
            ATTR_VALUE: 50,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.cfos_charging_manager_flag_1"},
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.cfos_charging_manager_load_management"},
        blocking=True,
    )

    assert writes == [
        (40968, float_words(50.0)),
        (40972, [1]),
        (40964, float_words(0.0)),
    ]
    assert (
        hass.states.get("number.cfos_charging_manager_total_current_limit").state
        == "50.0"
    )
    assert hass.states.get("switch.cfos_charging_manager_flag_1").state == STATE_ON


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_with_manager")
async def test_flash_parameters_skip_unchanged_writes(
    hass: HomeAssistant, manager_unit: MockModbusUnit
) -> None:
    writes = record_writes(manager_unit)

    for value in (63.0, 50.0):
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.cfos_charging_manager_maximum_total_current",
                ATTR_VALUE: value,
            },
            blocking=True,
        )

    assert writes == [(40954, float_words(50000.0))]


async def test_set_variable(
    hass: HomeAssistant,
    init_with_manager: MockConfigEntry,
    manager_unit: MockModbusUnit,
) -> None:
    writes = record_writes(manager_unit)

    await hass.services.async_call(
        DOMAIN,
        "set_charging_manager_variable",
        {"name": "night_rate", "value": 0.25},
        blocking=True,
    )
    assert writes == [(41004 + 2 + 22 + 20, float_words(0.25))]
    assert (
        hass.states.get("sensor.cfos_charging_manager_variable_night_rate").state
        == "0.25"
    )

    with pytest.raises(ServiceValidationError, match="pv_mode, night_rate"):
        await hass.services.async_call(
            DOMAIN,
            "set_charging_manager_variable",
            {"config_entry_id": init_with_manager.entry_id, "name": "x", "value": 1},
            blocking=True,
        )


@pytest.mark.usefixtures("init_integration")
async def test_set_variable_without_charging_manager(hass: HomeAssistant) -> None:
    with pytest.raises(ServiceValidationError, match="not enabled"):
        await hass.services.async_call(
            DOMAIN,
            "set_charging_manager_variable",
            {"name": "pv_mode", "value": 1},
            blocking=True,
        )


async def test_server_off_at_startup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    manager_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """The wallbox comes up; the Charging Manager joins once its server answers."""
    manager_unit.fail_requests(ModbusConnectionError("refused"))
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options=MANAGER_OPTIONS)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"
    assert hass.states.get("sensor.cfos_charging_manager_grid_power") is None

    manager_unit.fail_requests(None)
    await poll(hass, freezer)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert (
        float(hass.states.get("sensor.cfos_charging_manager_grid_power").state) == 2500
    )


@pytest.mark.usefixtures("init_with_manager")
async def test_models_moved_sets_up_again(
    hass: HomeAssistant,
    manager_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    """A firmware update that grows a model moves the ones behind it."""
    image: dict[int, Any] = charging_manager()
    words = image[40000]
    # Model 1 grows by two registers: everything behind it moves up.
    common_length = words[3]
    moved = [*words[: 4 + common_length], 0, 0, *words[4 + common_length :]]
    moved[3] = common_length + 2
    manager_unit.holding.clear()
    manager_unit.holding.update({40000: moved})

    await poll(hass, freezer)
    await hass.async_block_till_done()

    # Set up again, the scan found the models at their new addresses.
    assert (
        float(hass.states.get("sensor.cfos_charging_manager_grid_power").state) == 2500
    )


async def test_unavailable_while_unreachable(
    hass: HomeAssistant,
    init_with_manager: MockConfigEntry,
    manager_unit: MockModbusUnit,
    freezer: FrozenDateTimeFactory,
) -> None:
    manager_unit.fail_requests(ModbusConnectionError("gone"))
    await poll(hass, freezer)

    assert (
        hass.states.get("sensor.cfos_charging_manager_grid_power").state
        == STATE_UNAVAILABLE
    )
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"


async def test_diagnostics(
    hass: HomeAssistant,
    hass_client: ClientSessionGenerator,
    init_with_manager: MockConfigEntry,
) -> None:
    result = await get_diagnostics_for_config_entry(
        hass, hass_client, init_with_manager
    )

    manager = result["charging_manager"]
    assert manager["firmware"] == "2.1.4"
    assert [model["id"] for model in manager["models"]] == [
        1,
        *[213] * 7,
        60000,
        60001,
        60002,
    ]
    assert manager["models"][8]["address"] == 40952
    assert manager["variable_layout"] == "CmVariables"
    assert manager["registers"]["holding"]["40052"] == "**REDACTED**"
    assert CM_SERIAL not in str(result)


async def test_variables_with_names_alike_get_their_own_ids(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    manager_unit: MockModbusUnit,
    entity_registry: er.EntityRegistry,
) -> None:
    manager_unit.holding.update(charging_manager(variables=("PV Mode", "pv_mode")))
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(config_entry, options=MANAGER_OPTIONS)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    unique_ids = {
        entry.unique_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
        if "_variable_" in entry.unique_id
    }
    assert unique_ids == {
        f"{SERIAL}_charging_manager_variable_pv_mode",
        f"{SERIAL}_charging_manager_variable_pv_mode_2",
    }
