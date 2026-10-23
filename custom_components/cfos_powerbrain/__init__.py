"""The cFos Power Brain integration, over Modbus TCP."""

from __future__ import annotations

from datetime import timedelta
import logging

from modbus_connection import ModbusTcpParams

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant
from homeassistant.helpers import device_registry as dr
from homeassistant.helpers.device_registry import DeviceInfo

from .cfos_modbus import S0_METER_PORTS, S0_METER_UNIT_IDS, CfosS0Meter, CfosWallbox
from .const import (
    CONF_S0_METERS,
    CONF_UNIT_ID,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    MANUFACTURER,
    SETTINGS_SCAN_INTERVAL,
)
from .coordinator import CfosConfigEntry, CfosCoordinator, CfosRuntimeData, CfosUnitData

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [
    Platform.BINARY_SENSOR,
    Platform.BUTTON,
    Platform.NUMBER,
    Platform.SELECT,
    Platform.SENSOR,
    Platform.SWITCH,
]


async def async_setup_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Set up a cFos Power Brain from a config entry."""
    serial = entry.unique_id
    assert serial is not None
    host: str = entry.data[CONF_HOST]
    interval = timedelta(
        seconds=entry.options.get(CONF_SCAN_INTERVAL, DEFAULT_SCAN_INTERVAL)
    )

    wallbox = CfosWallbox(
        async_get_unit(
            hass,
            entry,
            ModbusTcpParams(host=host, port=entry.data[CONF_PORT]),
            entry.data[CONF_UNIT_ID],
        )
    )
    readings = CfosCoordinator(
        hass, entry, wallbox, wallbox.async_update_readings, interval, entry.title
    )
    settings = CfosCoordinator(
        hass,
        entry,
        wallbox,
        wallbox.async_update_settings,
        SETTINGS_SCAN_INTERVAL,
        f"{entry.title} settings",
    )
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
                model=identity.name or "Power Brain",
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
            async_get_unit(
                hass,
                entry,
                ModbusTcpParams(host=host, port=S0_METER_PORTS[number]),
                S0_METER_UNIT_IDS[number],
            )
        )
        meter_readings = CfosCoordinator(
            hass,
            entry,
            meter,
            meter.async_update_readings,
            interval,
            f"{entry.title} S0 meter {number}",
        )
        meter_settings = CfosCoordinator(
            hass,
            entry,
            meter,
            meter.async_update_settings,
            SETTINGS_SCAN_INTERVAL,
            f"{entry.title} S0 meter {number} settings",
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

    entry.runtime_data = runtime_data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def async_unload_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Unload a config entry; the modbus integration closes the connections."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
