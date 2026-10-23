"""Quality scale rules that hold for every entity, with every device set up."""

from __future__ import annotations

from datetime import timedelta

from freezegun.api import FrozenDateTimeFactory
from modbus_connection import ModbusTimeoutError
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant_custom_component.common import (
    MockConfigEntry,
    async_fire_time_changed,
)

from homeassistant.const import STATE_UNAVAILABLE
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import Entity
from homeassistant.helpers.entity_platform import async_get_platforms

from custom_components.cfos_powerbrain.const import (
    CONF_CHARGING_MANAGER,
    CONF_CHARGING_MANAGER_PORT,
    CONF_CHARGING_MANAGER_UNIT_ID,
    CONF_S0_METERS,
    DOMAIN,
    SETTINGS_SCAN_INTERVAL,
)


@pytest.fixture
async def entities(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
    entity_registry_enabled_by_default: None,
) -> list[Entity]:
    """Every entity, with both S0 meters and the Charging Manager."""
    config_entry.add_to_hass(hass)
    hass.config_entries.async_update_entry(
        config_entry,
        options={
            CONF_S0_METERS: ["1", "2"],
            CONF_CHARGING_MANAGER: True,
            CONF_CHARGING_MANAGER_PORT: 502,
            CONF_CHARGING_MANAGER_UNIT_ID: 1,
        },
    )
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return [
        entity
        for platform in async_get_platforms(hass, DOMAIN)
        for entity in platform.entities.values()
    ]


async def test_entity_unique_id_and_name(entities: list[Entity]) -> None:
    """Bronze: entity-unique-id and has-entity-name."""
    assert entities
    for entity in entities:
        assert entity.unique_id, entity.entity_id
        assert entity.has_entity_name, entity.entity_id


async def test_entity_unavailable(
    hass: HomeAssistant,
    entities: list[Entity],
    mock_modbus: dict[int, MockModbusConnection],
    freezer: FrozenDateTimeFactory,
) -> None:
    """Silver: entity-unavailable, for every entity once nothing answers."""
    # The units of the connections fixture: wallbox, S0 meters, Charging Manager.
    for port, unit_id in {4701: 1, 4702: 2, 4703: 3, 502: 1}.items():
        mock_modbus[port].for_unit(unit_id).fail_requests(ModbusTimeoutError("gone"))
    # Past the settings interval too, so every coordinator has polled.
    freezer.tick(SETTINGS_SCAN_INTERVAL + timedelta(seconds=1))
    async_fire_time_changed(hass)
    await hass.async_block_till_done()

    for entity in entities:
        state = hass.states.get(entity.entity_id)
        assert state is not None, entity.entity_id
        assert state.state == STATE_UNAVAILABLE, entity.entity_id
