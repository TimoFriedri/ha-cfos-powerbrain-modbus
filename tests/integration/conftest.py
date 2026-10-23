"""Fixtures for the integration tests.

The integration asks Home Assistant's modbus integration for its units, so
only the transport underneath is replaced: each TCP port of the wallbox gets
an in-memory mock connection seeded with a register image.
"""

from __future__ import annotations

from collections.abc import Generator
from unittest.mock import PropertyMock, patch

from modbus_connection import ModbusTcpParams
from modbus_connection.mock import MockModbusConnection
import pytest
from pytest_homeassistant_custom_component.common import MockConfigEntry

from homeassistant.const import CONF_HOST, CONF_PORT
from homeassistant.core import HomeAssistant

from custom_components.cfos_powerbrain.const import CONF_UNIT_ID, DOMAIN
from tests.registers import SERIAL, charging_manager, s0_meter, wallbox

HOST = "192.168.1.50"
ENTRY_DATA = {CONF_HOST: HOST, CONF_PORT: 4701, CONF_UNIT_ID: 1}


@pytest.fixture(autouse=True)
def auto_enable_custom_integrations(enable_custom_integrations: None) -> None:
    """Load the integration from custom_components."""


@pytest.fixture
def entity_registry_enabled_by_default() -> Generator[None]:
    """Create the entities that are disabled by default as enabled."""
    with patch(
        "homeassistant.helpers.entity.Entity.entity_registry_enabled_default",
        new_callable=PropertyMock,
        return_value=True,
    ):
        yield


class ReopenableMockConnection(MockModbusConnection):
    """A mock connection that opens again after it was closed.

    Home Assistant builds a new connection for a device once the last hold
    on the old one is released. Reopening the same mock stands in for that
    and keeps the register image and injected failures in place.
    """

    closed_count = 0

    async def close(self) -> None:
        """Close the link, but allow a later hold to use it again."""
        await super().close()
        self.closed_count += 1
        self._closed = False


@pytest.fixture
def connections() -> dict[int, MockModbusConnection]:
    """One mock connection per TCP port, keyed by port."""
    evse = ReopenableMockConnection()
    evse.for_unit(1).holding.update(wallbox())
    s0_1 = ReopenableMockConnection()
    s0_1.for_unit(2).holding.update(s0_meter(0x101))
    s0_2 = ReopenableMockConnection()
    s0_2.for_unit(3).holding.update(s0_meter(0x102))
    manager = ReopenableMockConnection()
    manager.for_unit(1).holding.update(charging_manager())
    return {4701: evse, 4702: s0_1, 4703: s0_2, 502: manager}


@pytest.fixture
def mock_modbus(
    connections: dict[int, MockModbusConnection],
) -> Generator[dict[int, MockModbusConnection]]:
    """Back the modbus integration's shared connections with the mocks."""

    def connect(params: ModbusTcpParams) -> MockModbusConnection:
        return connections[params.port]

    with patch(
        "homeassistant.components.modbus.connection.ModbusConnection",
        side_effect=connect,
    ):
        yield connections


@pytest.fixture
def config_entry() -> MockConfigEntry:
    """A config entry for the wallbox."""
    return MockConfigEntry(
        domain=DOMAIN,
        unique_id=SERIAL,
        data=ENTRY_DATA,
        title="cFos Power Brain Wallbox",
        minor_version=2,
    )


@pytest.fixture
async def init_integration(
    hass: HomeAssistant,
    config_entry: MockConfigEntry,
    mock_modbus: dict[int, MockModbusConnection],
) -> MockConfigEntry:
    """Set up the integration against the mock wallbox."""
    config_entry.add_to_hass(hass)
    assert await hass.config_entries.async_setup(config_entry.entry_id)
    await hass.async_block_till_done()
    return config_entry
