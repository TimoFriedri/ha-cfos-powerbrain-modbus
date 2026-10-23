"""Setting up and unloading a config entry."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import (
    IllegalDataAddressError,
    ModbusConnectionError,
    ModbusTimeoutError,
)
from modbus_connection.mock import MockModbusConnection
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr, entity_registry as er

from custom_components.cfos_powerbrain.const import CONF_S0_METERS, DOMAIN
from tests.integration.conftest import ENTRY_DATA, ReopenableMockConnection
from tests.registers import SERIAL


async def test_setup_and_unload(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
    device_registry: dr.DeviceRegistry,
) -> None:
    assert init_integration.state is ConfigEntryState.LOADED

    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), init_integration.entry_id
    )
    assert device is not None
    assert device.manufacturer == "cFos"
    assert device.model == "cFos Power Brain Controller"
    assert device.sw_version == "1.25.3"
    assert device.serial_number == SERIAL

    assert await hass.config_entries.async_unload(init_integration.entry_id)
    assert init_integration.state is ConfigEntryState.NOT_LOADED
    # The modbus integration closed the connection behind the last holder.
    connection = mock_modbus[4701]
    assert isinstance(connection, ReopenableMockConnection)
    assert connection.closed_count >= 1


async def test_setup_retries_while_unreachable(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    mock_modbus[4701].for_unit(1).fail_requests(ModbusConnectionError("refused"))
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_RETRY


async def test_setup_fails_for_other_vendor(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    mock_modbus[4701].for_unit(1).holding[8000] = [0, 0x1234]
    config_entry.add_to_hass(hass)

    await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.SETUP_ERROR


async def test_refused_settings_block_does_not_block_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    mock_modbus[4701].for_unit(1).fail_read(8080, IllegalDataAddressError())
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"


async def test_outage_and_recovery(
    hass: HomeAssistant,
    init_integration: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
    freezer: FrozenDateTimeFactory,
) -> None:
    unit = mock_modbus[4701].for_unit(1)
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"

    unit.fail_requests(ModbusTimeoutError("no answer"))
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert (
        hass.states.get("sensor.cfos_power_brain_wallbox_power").state
        == STATE_UNAVAILABLE
    )
    # A lifetime total keeps its value, so statistics have no gap.
    assert (
        hass.states.get("sensor.cfos_power_brain_wallbox_total_energy").state
        == "1234.567"
    )

    unit.fail_requests(None)
    freezer.tick(timedelta(seconds=11))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"


async def test_s0_meters(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
    device_registry: dr.DeviceRegistry,
) -> None:
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_S0_METERS: ["1", "2"]}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    wallbox = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), config_entry.entry_id
    )
    meter = device_registry.async_get_device_by_identifier(
        (DOMAIN, f"{SERIAL}_s0_2"), config_entry.entry_id
    )
    assert wallbox is not None
    assert meter is not None
    assert meter.via_device_id == wallbox.id

    assert hass.states.get("sensor.s0_meter_1_power").state == "3000"
    assert hass.states.get("sensor.s0_meter_2_total_energy").state == "5000.0"


async def test_unanswering_s0_meter_does_not_block_setup(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> None:
    mock_modbus[4702].for_unit(2).fail_requests(ModbusTimeoutError("no answer"))
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry, options={CONF_S0_METERS: ["1"]}
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()

    assert config_entry.state is ConfigEntryState.LOADED
    assert hass.states.get("sensor.s0_meter_1_power").state == STATE_UNAVAILABLE
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"


async def test_entry_from_0_2_is_left_as_it_is(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    entity_registry: er.EntityRegistry,
) -> None:
    """Nothing is migrated: an older entry keeps its title and entity IDs."""
    entry = MockConfigEntry(
        domain=DOMAIN, unique_id=SERIAL, data=ENTRY_DATA, title="cFos Power Brain"
    )
    entry.add_to_hass(hass)
    entity_registry.async_get_or_create(
        "sensor",
        DOMAIN,
        f"{SERIAL}_power",
        suggested_object_id="cfos_power_brain_power",
        config_entry=entry,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.title == "cFos Power Brain"
    assert hass.states.get("sensor.cfos_power_brain_power").state == "7360"
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power") is None
