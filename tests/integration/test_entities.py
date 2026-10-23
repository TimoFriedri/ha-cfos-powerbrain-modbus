"""Entity states and the writes they make."""

from __future__ import annotations

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection, MockModbusUnit
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
)

from homeassistant.components.button import SERVICE_PRESS
from homeassistant.components.number import ATTR_VALUE, SERVICE_SET_VALUE
from homeassistant.components.select import ATTR_OPTION, SERVICE_SELECT_OPTION
from homeassistant.const import (
    ATTR_ENTITY_ID,
    SERVICE_TURN_OFF,
    SERVICE_TURN_ON,
    STATE_OFF,
    STATE_ON,
)
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers import entity_registry as er

from tests.integration.conftest import poll
from tests.registers import record_writes, wallbox, words


@pytest.fixture
def evse(mock_modbus: dict[int, MockModbusConnection]) -> MockModbusUnit:
    return mock_modbus[4701].for_unit(1)


@pytest.mark.usefixtures("init_integration")
async def test_states(hass: HomeAssistant) -> None:
    expected = {
        "sensor.cfos_power_brain_wallbox_charging_state": "charging",
        "sensor.cfos_power_brain_wallbox_signaled_charging_current": "16.0",
        "sensor.cfos_power_brain_wallbox_power": "7360",
        "sensor.cfos_power_brain_wallbox_total_energy": "1234.567",
        "sensor.cfos_power_brain_wallbox_current_l1": "10.7",
        "sensor.cfos_power_brain_wallbox_current_l3": "10.8",
        "sensor.cfos_power_brain_wallbox_active_phases": "3",
        "sensor.cfos_power_brain_wallbox_session_energy": "0.0",
        "sensor.cfos_power_brain_wallbox_controller_temperature": "35",
        "binary_sensor.cfos_power_brain_wallbox_vehicle_connected": STATE_ON,
        "binary_sensor.cfos_power_brain_wallbox_charging": STATE_ON,
        "binary_sensor.cfos_power_brain_wallbox_problem": STATE_OFF,
        "switch.cfos_power_brain_wallbox_charging_enabled": STATE_ON,
        "number.cfos_power_brain_wallbox_charging_current_limit": "16.0",
        "select.cfos_power_brain_wallbox_phase_mode": "three_phase",
    }
    for entity_id, state in expected.items():
        assert (current := hass.states.get(entity_id)) is not None, entity_id
        assert current.state == state, entity_id

    # Settings that go to flash are hidden until enabled.
    assert hass.states.get("number.cfos_power_brain_wallbox_fail_safe_current") is None
    assert hass.states.get("sensor.cfos_power_brain_wallbox_last_rfid") is None


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_hidden_entities(hass: HomeAssistant) -> None:
    expected = {
        "sensor.cfos_power_brain_wallbox_last_rfid": "04A1B2C3D4",
        "number.cfos_power_brain_wallbox_fail_safe_current": "6.0",
        "number.cfos_power_brain_wallbox_fail_safe_timeout": "300",
        "switch.cfos_power_brain_wallbox_default_charging_enabled": STATE_ON,
    }
    for entity_id, state in expected.items():
        assert (current := hass.states.get(entity_id)) is not None, entity_id
        assert current.state == state, entity_id


async def test_optional_entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    evse: MockModbusUnit,
    entity_registry: er.EntityRegistry,
) -> None:
    """A wallbox without meter, phase switching or relay 2 gets no entities for them."""
    evse.holding.update(wallbox(has_meter=False, s0_inputs=0))
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    entity_ids = {
        entry.entity_id
        for entry in er.async_entries_for_config_entry(
            entity_registry, config_entry.entry_id
        )
    }
    assert "sensor.cfos_power_brain_wallbox_power" not in entity_ids
    assert "sensor.cfos_power_brain_wallbox_session_energy" not in entity_ids
    assert "select.cfos_power_brain_wallbox_phase_mode" not in entity_ids
    assert "switch.cfos_power_brain_wallbox_relay_2" not in entity_ids
    assert "switch.cfos_power_brain_wallbox_charging_enabled" in entity_ids


async def test_relay2_switch(
    hass: HomeAssistant, config_entry: MockConfigEntry, evse: MockModbusUnit
) -> None:
    evse.holding[8113] = 0b0110_0000_0000  # presence known, relay 2 fitted
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    writes = record_writes(evse)

    await hass.services.async_call(
        "switch",
        SERVICE_TURN_ON,
        {ATTR_ENTITY_ID: "switch.cfos_power_brain_wallbox_relay_2"},
        blocking=True,
    )
    assert writes == [(8088, [1])]


@pytest.mark.usefixtures("init_integration")
async def test_controls_write_volatile_registers(
    hass: HomeAssistant, evse: MockModbusUnit
) -> None:
    writes = record_writes(evse)

    await hass.services.async_call(
        "number",
        SERVICE_SET_VALUE,
        {
            ATTR_ENTITY_ID: "number.cfos_power_brain_wallbox_charging_current_limit",
            ATTR_VALUE: 10.7,
        },
        blocking=True,
    )
    await hass.services.async_call(
        "switch",
        SERVICE_TURN_OFF,
        {ATTR_ENTITY_ID: "switch.cfos_power_brain_wallbox_charging_enabled"},
        blocking=True,
    )
    await hass.services.async_call(
        "select",
        SERVICE_SELECT_OPTION,
        {
            ATTR_ENTITY_ID: "select.cfos_power_brain_wallbox_phase_mode",
            ATTR_OPTION: "single_phase",
        },
        blocking=True,
    )
    await hass.services.async_call(
        "button",
        SERVICE_PRESS,
        {ATTR_ENTITY_ID: "button.cfos_power_brain_wallbox_wake_up_vehicle"},
        blocking=True,
    )
    await hass.async_block_till_done()

    assert writes == [(8093, [107]), (8094, [0]), (8087, [1]), (8086, [5])]
    assert (
        hass.states.get("number.cfos_power_brain_wallbox_charging_current_limit").state
        == "10.7"
    )
    assert (
        hass.states.get("switch.cfos_power_brain_wallbox_charging_enabled").state
        == "off"
    )


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_flash_settings_skip_unchanged_writes(
    hass: HomeAssistant, evse: MockModbusUnit
) -> None:
    writes = record_writes(evse)
    entity_id = "number.cfos_power_brain_wallbox_default_charging_current_limit"

    for value in (16.0, 10.0):
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {ATTR_ENTITY_ID: entity_id, ATTR_VALUE: value},
            blocking=True,
        )

    assert writes == [(8081, [100])]


@pytest.mark.usefixtures("entity_registry_enabled_by_default", "init_integration")
async def test_rejected_value(hass: HomeAssistant, evse: MockModbusUnit) -> None:
    writes = record_writes(evse)

    with pytest.raises(HomeAssistantError, match="does not accept"):
        await hass.services.async_call(
            "number",
            SERVICE_SET_VALUE,
            {
                ATTR_ENTITY_ID: "number.cfos_power_brain_wallbox_cable_current_override",
                ATTR_VALUE: 3,
            },
            blocking=True,
        )
    assert writes == []


@pytest.mark.usefixtures("init_integration")
async def test_failed_write(hass: HomeAssistant, evse: MockModbusUnit) -> None:
    evse.fail_write(8094, ModbusTimeoutError("no answer"))

    with pytest.raises(HomeAssistantError, match="Writing to the wallbox failed"):
        await hass.services.async_call(
            "switch",
            SERVICE_TURN_OFF,
            {ATTR_ENTITY_ID: "switch.cfos_power_brain_wallbox_charging_enabled"},
            blocking=True,
        )


@pytest.mark.usefixtures("init_integration")
async def test_session_energy(
    hass: HomeAssistant, evse: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    entity_id = "sensor.cfos_power_brain_wallbox_session_energy"
    assert hass.states.get(entity_id).state == "0.0"

    evse.holding[8058] = words(1_234_567 + 1500, 4)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "1.5"

    # Unplugged: the finished session stays.
    evse.holding[8092] = 0
    evse.holding[8058] = words(1_234_567 + 1600, 4)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "1.5"

    # The next vehicle starts a new session.
    evse.holding[8092] = 1
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "0.0"

    evse.holding[8092] = 2
    evse.holding[8058] = words(1_234_567 + 1600 + 250, 4)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "0.25"


@pytest.mark.usefixtures("init_integration")
async def test_total_energy_ignores_glitch(
    hass: HomeAssistant, evse: MockModbusUnit, freezer: FrozenDateTimeFactory
) -> None:
    entity_id = "sensor.cfos_power_brain_wallbox_total_energy"

    # 0 Wh right after a controller restart reads as unknown, not a reset.
    evse.holding[8058] = words(0, 4)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "1234.567"

    evse.holding[8058] = words(1_234_000, 4)  # a hair below the last value
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "1234.567"

    evse.holding[8058] = words(1_240_000, 4)
    await poll(hass, freezer)
    assert hass.states.get(entity_id).state == "1240.0"
