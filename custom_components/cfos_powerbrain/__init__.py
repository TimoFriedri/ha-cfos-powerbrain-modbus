"""The cFos Power Brain Wallbox integration, over Modbus TCP."""

from __future__ import annotations

from datetime import timedelta
import logging

from modbus_connection import ModbusTcpParams

from homeassistant.components.modbus import async_get_unit
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL, Platform
from homeassistant.core import HomeAssistant, callback, split_entity_id
from homeassistant.helpers import (
    config_validation as cv,
    device_registry as dr,
    entity_registry as er,
    restore_state,
)
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.typing import ConfigType
from homeassistant.util import slugify

from .cfos_modbus import (
    DEFAULT_CHARGING_MANAGER_PORT,
    DEFAULT_CHARGING_MANAGER_UNIT_ID,
    S0_METER_PORTS,
    S0_METER_UNIT_IDS,
    CfosChargingManager,
    CfosS0Meter,
    CfosWallbox,
)
from .const import (
    CONF_CHARGING_MANAGER,
    CONF_CHARGING_MANAGER_PORT,
    CONF_CHARGING_MANAGER_UNIT_ID,
    CONF_S0_METERS,
    CONF_UNIT_ID,
    DEFAULT_NAME,
    DEFAULT_SCAN_INTERVAL,
    DOMAIN,
    FORMER_DEFAULT_NAME,
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


async def async_migrate_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Migrate an entry from an older version of the integration."""
    if entry.version > 1:
        return False  # from a newer version; downgrading is not supported
    if entry.minor_version < 2:
        # 0.3.0 names the device like cFos does; a title the user chose stays.
        title = DEFAULT_NAME if entry.title == FORMER_DEFAULT_NAME else entry.title
        hass.config_entries.async_update_entry(entry, title=title, minor_version=2)
    if entry.minor_version < 3:
        # The entity IDs follow the new names too. The recorder carries history
        # and statistics over to the renamed IDs.
        if entry.title == DEFAULT_NAME:
            _async_rename_entity_ids(
                hass,
                entry,
                f"{slugify(FORMER_DEFAULT_NAME)}_",
                f"{slugify(DEFAULT_NAME)}_",
            )
        # The Charging Manager device was named "cFos Lademanager" in German.
        _async_rename_entity_ids(
            hass, entry, "cfos_lademanager_", "cfos_charging_manager_"
        )
        hass.config_entries.async_update_entry(entry, minor_version=3)
    return True


@callback
def _async_rename_entity_ids(
    hass: HomeAssistant, entry: CfosConfigEntry, old_prefix: str, new_prefix: str
) -> None:
    """Rename the entry's entity IDs that start with ``old_prefix``.

    An ID the user changed to something else no longer starts with the prefix
    and stays as it is, as does one whose new ID is already taken. The state
    kept for restoring, such as a session in progress, moves along.
    """
    registry = er.async_get(hass)
    restorable = restore_state.async_get(hass).last_states
    for entity in er.async_entries_for_config_entry(registry, entry.entry_id):
        domain, object_id = split_entity_id(entity.entity_id)
        if not object_id.startswith(old_prefix) or object_id.startswith(new_prefix):
            continue
        new_entity_id = f"{domain}.{new_prefix}{object_id.removeprefix(old_prefix)}"
        if registry.async_get(new_entity_id) is not None:
            _LOGGER.warning(
                "Keeping %s: %s is already taken", entity.entity_id, new_entity_id
            )
            continue
        registry.async_update_entity(entity.entity_id, new_entity_id=new_entity_id)
        if (stored := restorable.pop(entity.entity_id, None)) is not None:
            restorable[new_entity_id] = stored


async def async_setup_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Set up a cFos Power Brain Wallbox from a config entry."""
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

    if entry.options.get(CONF_CHARGING_MANAGER):
        runtime_data.charging_manager = await _async_setup_charging_manager(
            hass, entry, host, serial, interval
        )

    entry.runtime_data = runtime_data
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    return True


async def _async_setup_charging_manager(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    host: str,
    serial: str,
    interval: timedelta,
) -> CfosUnitData[CfosChargingManager]:
    """Reach the Charging Manager through its SunSpec server, next to the wallbox."""
    manager = CfosChargingManager(
        async_get_unit(
            hass,
            entry,
            ModbusTcpParams(
                host=host,
                port=entry.options.get(
                    CONF_CHARGING_MANAGER_PORT, DEFAULT_CHARGING_MANAGER_PORT
                ),
            ),
            entry.options.get(
                CONF_CHARGING_MANAGER_UNIT_ID, DEFAULT_CHARGING_MANAGER_UNIT_ID
            ),
        )
    )
    readings = CfosCoordinator(
        hass,
        entry,
        manager,
        manager.async_update_readings,
        interval,
        f"{entry.title} Charging Manager",
        optional=True,
    )
    settings = CfosCoordinator(
        hass,
        entry,
        manager,
        manager.async_update_settings,
        SETTINGS_SCAN_INTERVAL,
        f"{entry.title} Charging Manager settings",
        optional=True,
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
            configuration_url=f"http://{host}",
        ),
        unique_id_prefix=f"{serial}_charging_manager",
    )


async def async_unload_entry(hass: HomeAssistant, entry: CfosConfigEntry) -> bool:
    """Unload a config entry; the modbus integration closes the connections."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
