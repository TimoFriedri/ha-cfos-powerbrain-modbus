"""The cFos Power Brain Wallbox integration, over Modbus TCP."""

from __future__ import annotations

from datetime import timedelta
import logging

from modbus_connection import ModbusTcpParams, ModbusUnit

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers import config_validation as cv, device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType

from .cfos_modbus import (
    S0_METER_PORTS,
    S0_METER_UNIT_IDS,
    CfosChargingManager,
    CfosDevice,
    CfosS0Meter,
    CfosWallbox,
)
from .const import (
    CONF_CHARGING_MANAGER,
    CONF_CHARGING_MANAGER_PORT,
    CONF_CHARGING_MANAGER_UNIT_ID,
    CONF_S0_METERS,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SETTINGS_SCAN_INTERVAL,
)
from .coordinator import CfosConfigEntry, CfosCoordinator, CfosRuntimeData, CfosUnitData
from .services import async_setup_services

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]

CONFIG_SCHEMA = cv.config_entry_only_config_schema(DOMAIN)


async def async_setup(hass: HomeAssistant, config: ConfigType) -> bool:
    """Register the actions, whether or not an entry is loaded."""
    async_setup_services(hass)
    return True


async def async_setup_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Set up a cFos Power Brain Wallbox from a config entry."""
    serial = entry.unique_id
    assert serial is not None
    host: str = entry.data[CONF_HOST]
    interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    wallbox = CfosWallbox(
        _async_get_unit(hass, entry, entry.data[CONF_PORT], entry.data[CONF_UNIT_ID])
    )
    readings, settings = _coordinators(hass, entry, wallbox, interval, entry.title)
    # The first read identifies the wallbox and settles its optional blocks,
    # which decides the entities, so it must succeed before them. The
    # settings are not needed for that; their entities go unavailable while
    # the settings block does not answer instead of holding up the rest.
    await readings.async_config_entry_first_refresh()
    await settings.async_refresh()

    identity = wallbox.identity
    runtime_data = CfosRuntimeData(
        wallbox=CfosUnitData(
            device=wallbox,
            readings=readings,
            settings=settings,
            device_info=DeviceInfo(
                identifiers={(DOMAIN, serial)},
                manufacturer=MANUFACTURER,
                model=identity.name or "cFos Power Brain Controller",
                name=entry.title,
                serial_number=serial,
                sw_version=identity.firmware_version,
                configuration_url=f"http://{host}",
            ),
            unique_id_prefix=serial,
        )
    )
    # Registered up front: the S0 meters name it as the device they sit on.
    wallbox_device = dr.async_get(hass).async_get_or_create(
        config_entry_id=entry.entry_id, **runtime_data.wallbox.device_info
    )

    for number in sorted(int(n) for n in entry.options.get(CONF_S0_METERS, [])):
        meter = CfosS0Meter(
            _async_get_unit(
                hass, entry, S0_METER_PORTS[number], S0_METER_UNIT_IDS[number]
            )
        )
        meter_readings, meter_settings = _coordinators(
            hass, entry, meter, interval, f"{entry.title} S0 meter {number}"
        )
        # An S0 meter is an optional extra: its entities go unavailable while
        # it does not answer instead of holding up the wallbox.
        await meter_readings.async_refresh()
        await meter_settings.async_refresh()
        runtime_data.s0_meters[number] = CfosUnitData(
            device=meter,
            readings=meter_readings,
            settings=meter_settings,
            device_info=DeviceInfo(
                identifiers={(DOMAIN, f"{serial}_s0_{number}")},
                manufacturer=MANUFACTURER,
                translation_key="s0_meter",
                translation_placeholders={"number": str(number)},
                via_device_id=wallbox_device.id,
            ),
            unique_id_prefix=f"{serial}_s0_{number}",
        )

    if entry.options.get(CONF_CHARGING_MANAGER):
        runtime_data.charging_manager = await _async_setup_charging_manager(
            hass, entry, serial, interval
        )

    entry.runtime_data = runtime_data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_setup_charging_manager(
    hass: HomeAssistant, entry: CfosConfigEntry, serial: str, interval: timedelta
) -> CfosUnitData[CfosChargingManager]:
    """Reach the Charging Manager through its SunSpec server, next to the wallbox."""
    manager = CfosChargingManager(
        _async_get_unit(
            hass,
            entry,
            entry.options[CONF_CHARGING_MANAGER_PORT],
            entry.options[CONF_CHARGING_MANAGER_UNIT_ID],
        )
    )
    readings, settings = _coordinators(
        hass, entry, manager, interval, f"{entry.title} Charging Manager", optional=True
    )
    await readings.async_refresh()
    if readings.last_update_success:
        await settings.async_refresh()
    else:
        _LOGGER.warning(
            "%s: the Charging Manager's SunSpec server does not answer yet; its "
            "entities are added once it does",
            entry.title,
        )

        # Its entities follow the models the scan finds, so set up again
        # once the server answers rather than leaving them out.
        @callback
        def _async_reload_once_answered() -> None:
            if readings.last_update_success:
                hass.config_entries.async_schedule_reload(entry.entry_id)

        entry.async_on_unload(readings.async_add_listener(_async_reload_once_answered))

    common = manager.common
    return CfosUnitData(
        device=manager,
        readings=readings,
        settings=settings,
        device_info=DeviceInfo(
            identifiers={(DOMAIN, f"{serial}_charging_manager")},
            manufacturer=MANUFACTURER,
            model=(common.model if common else None) or "Charging Manager",
            translation_key="charging_manager",
            sw_version=manager.firmware_version,
            configuration_url=f"http://{entry.data[CONF_HOST]}",
        ),
        unique_id_prefix=f"{serial}_charging_manager",
    )


@callback
def _async_get_unit(
    hass: HomeAssistant, entry: CfosConfigEntry, port: int, unit_id: int
) -> ModbusUnit:
    """A unit on the wallbox's host, over a connection the modbus integration shares."""
    params = ModbusTcpParams(host=entry.data[CONF_HOST], port=port)
    return async_get_unit(hass, entry, params, unit_id)


def _coordinators(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    device: CfosDevice,
    interval: timedelta,
    name: str,
    *,
    optional: bool = False,
) -> tuple[CfosCoordinator, CfosCoordinator]:
    """Coordinators for a unit's readings, every ``interval``, and its settings."""
    return (
        CfosCoordinator(
            hass, entry, device.async_update_readings, interval, name, optional=optional
        ),
        CfosCoordinator(
            hass,
            entry,
            device.async_update_settings,
            SETTINGS_SCAN_INTERVAL,
            f"{name} settings",
            optional=optional,
        ),
    )


async def async_unload_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Unload a config entry; the modbus integration closes the connections."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
