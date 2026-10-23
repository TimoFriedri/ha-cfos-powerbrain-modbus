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
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
    mock_restore_cache_with_extra_data,
)

from homeassistant.config_entries import ConfigEntryState
from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant, State
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


def _old_entry(
    hass: HomeAssistant,
    entity_registry: er.EntityRegistry,
    *,
    title: str = "cFos Power Brain",
    minor_version: int = 1,
    entity_ids: dict[str, str] | None = None,
) -> MockConfigEntry:
    """An entry as an older version left it, with its entities registered."""
    entry = MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        data=ENTRY_DATA,
        title=title,
        version=1,
        minor_version=minor_version,
    )
    entry.add_to_hass(hass)
    for unique_id, entity_id in (entity_ids or {}).items():
        domain, object_id = entity_id.split(".")
        entity_registry.async_get_or_create(
            domain,
            DOMAIN,
            unique_id,
            suggested_object_id=object_id,
            config_entry=entry,
        )
    return entry


OLD_ENTITY_IDS = {
    f"{SERIAL}_power": "sensor.cfos_power_brain_power",
    f"{SERIAL}_charging_enabled": "switch.cfos_power_brain_charging_enabled",
    f"{SERIAL}_charging_manager_grid_power": "sensor.cfos_lademanager_grid_power",
    f"{SERIAL}_s0_1_power": "sensor.s0_meter_1_power",
}


@pytest.mark.parametrize("minor_version", [1, 2])
async def test_migrate_to_the_cfos_product_names(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    device_registry: dr.DeviceRegistry,
    entity_registry: er.EntityRegistry,
    minor_version: int,
) -> None:
    """Entries from 0.2 (minor 1) and the first 0.3 build (minor 2) take the new names."""
    title = "cFos Power Brain" if minor_version == 1 else "cFos Power Brain Wallbox"
    entry = _old_entry(
        hass,
        entity_registry,
        title=title,
        minor_version=minor_version,
        entity_ids=OLD_ENTITY_IDS,
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.minor_version == 3
    assert entry.title == "cFos Power Brain Wallbox"
    device = device_registry.async_get_device_by_identifier(
        (DOMAIN, SERIAL), entry.entry_id
    )
    assert device is not None
    assert device.name == "cFos Power Brain Wallbox"

    ids = {
        unique_id: entity_registry.async_get_entity_id(
            entity_id.split(".")[0], DOMAIN, unique_id
        )
        for unique_id, entity_id in OLD_ENTITY_IDS.items()
    }
    assert ids == {
        f"{SERIAL}_power": "sensor.cfos_power_brain_wallbox_power",
        f"{SERIAL}_charging_enabled": "switch.cfos_power_brain_wallbox_charging_enabled",
        f"{SERIAL}_charging_manager_grid_power": "sensor.cfos_charging_manager_grid_power",
        f"{SERIAL}_s0_1_power": "sensor.s0_meter_1_power",  # not named after the wallbox
    }
    assert hass.states.get("sensor.cfos_power_brain_wallbox_power").state == "7360"


async def test_migrate_keeps_names_the_user_chose(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    entity_registry: er.EntityRegistry,
) -> None:
    entry = _old_entry(
        hass,
        entity_registry,
        title="Garage wallbox",
        entity_ids={
            f"{SERIAL}_power": "sensor.cfos_power_brain_power",
            f"{SERIAL}_charging_enabled": "switch.garage_charging",
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entry.title == "Garage wallbox"
    assert entity_registry.async_get("sensor.cfos_power_brain_power") is not None
    assert entity_registry.async_get("switch.garage_charging") is not None


async def test_migrate_skips_an_id_already_taken(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    entity_registry: er.EntityRegistry,
    caplog: pytest.LogCaptureFixture,
) -> None:
    entity_registry.async_get_or_create(
        "sensor",
        "template",
        "other",
        suggested_object_id="cfos_power_brain_wallbox_power",
    )
    entry = _old_entry(
        hass,
        entity_registry,
        entity_ids={f"{SERIAL}_power": "sensor.cfos_power_brain_power"},
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    assert entity_registry.async_get_entity_id("sensor", DOMAIN, f"{SERIAL}_power") == (
        "sensor.cfos_power_brain_power"
    )
    assert "sensor.cfos_power_brain_wallbox_power is already taken" in caplog.text


async def test_entry_from_a_newer_version_is_refused(
    hass: HomeAssistant, mock_modbus: dict[int, MockModbusConnection]
) -> None:
    entry = MockConfigEntry(domain=DOMAIN, unique_id=SERIAL, data=ENTRY_DATA, version=2)
    entry.add_to_hass(hass)
    assert not await hass.config_entries.async_setup(entry.entry_id)

    assert entry.state is ConfigEntryState.MIGRATION_ERROR


async def test_migrate_carries_a_session_over(
    hass: HomeAssistant,
    mock_modbus: dict[int, MockModbusConnection],
    entity_registry: er.EntityRegistry,
) -> None:
    """A charging session in progress keeps counting across the rename."""
    mock_restore_cache_with_extra_data(
        hass,
        [
            (
                State("sensor.cfos_power_brain_session_energy", "1.9"),
                {
                    "native_value": 1.9,
                    "start_energy": 1_234_567 - 2000,
                    "vehicle_connected": True,
                },
            )
        ],
    )
    entry = _old_entry(
        hass,
        entity_registry,
        entity_ids={
            f"{SERIAL}_session_energy": "sensor.cfos_power_brain_session_energy"
        },
    )
    assert await hass.config_entries.async_setup(entry.entry_id)
    await hass.async_block_till_done()

    state = hass.states.get("sensor.cfos_power_brain_wallbox_session_energy")
    assert state is not None
    assert state.state == "2.0"
