"""Actions of the cFos Power Brain integration."""

from __future__ import annotations

from modbus_connection import ModbusError
import probatio

from homeassistant.const import ATTR_CONFIG_ENTRY_ID, ATTR_NAME
from homeassistant.core import HomeAssistant, ServiceCall, callback
from homeassistant.exceptions import HomeAssistantError, ServiceValidationError
from homeassistant.helpers.service import (
    async_get_config_entry,
    async_register_admin_service,
)

from .const import DOMAIN
from .coordinator import CfosConfigEntry

SERVICE_SET_CHARGING_MANAGER_VARIABLE = "set_charging_manager_variable"

ATTR_VALUE = "value"

SET_CHARGING_MANAGER_VARIABLE_SCHEMA = probatio.Schema(
    {
        probatio.Optional(ATTR_CONFIG_ENTRY_ID): str,
        probatio.Required(ATTR_NAME): str,
        probatio.Required(ATTR_VALUE): probatio.Coerce(float),
    }
)


@callback
def async_setup_services(hass: HomeAssistant) -> None:
    """Register the actions."""

    async def _handle_set_charging_manager_variable(call: ServiceCall) -> None:
        """Give a Charging Manager variable a fixed value, replacing its formula."""
        entry: CfosConfigEntry = async_get_config_entry(
            hass, DOMAIN, call.data.get(ATTR_CONFIG_ENTRY_ID)
        )
        if (manager := entry.runtime_data.charging_manager) is None:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="charging_manager_not_enabled",
                translation_placeholders={"title": entry.title},
            )
        name = call.data[ATTR_NAME]
        try:
            await manager.device.async_set_variable(name, call.data[ATTR_VALUE])
        except KeyError as err:
            raise ServiceValidationError(
                translation_domain=DOMAIN,
                translation_key="unknown_variable",
                translation_placeholders={
                    "name": name,
                    "names": ", ".join(manager.device.variable_names) or "-",
                },
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await manager.readings.async_refresh()

    async_register_admin_service(
        hass,
        DOMAIN,
        SERVICE_SET_CHARGING_MANAGER_VARIABLE,
        _handle_set_charging_manager_variable,
        schema=SET_CHARGING_MANAGER_VARIABLE_SCHEMA,
    )
