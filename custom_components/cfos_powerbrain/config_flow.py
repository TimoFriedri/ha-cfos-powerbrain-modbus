"""Config flow for the cFos Power Brain Wallbox."""

from __future__ import annotations

import logging
from typing import Any

from modbus_connection import ModbusError, ModbusTcpParams
import probatio

from homeassistant.components.modbus import async_get_temporary_unit
from homeassistant.config_entries import (
    ConfigFlow,
    ConfigFlowResult,
    OptionsFlowWithReload,
)
from homeassistant.const import CONF_HOST, CONF_PORT, CONF_SCAN_INTERVAL
from homeassistant.core import HomeAssistant, callback
from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.selector import (
    BooleanSelector,
    NumberSelector,
    NumberSelectorConfig,
    NumberSelectorMode,
    SelectSelector,
    SelectSelectorConfig,
    TextSelector,
)

from .cfos_modbus import (
    DEFAULT_CHARGING_MANAGER_PORT,
    DEFAULT_CHARGING_MANAGER_UNIT_ID,
    DEFAULT_EVSE_PORT,
    DEFAULT_EVSE_UNIT_ID,
    S0_METER_PORTS,
    CfosChargingManager,
    CfosWallbox,
    UnsupportedDeviceError,
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
    MAX_SCAN_INTERVAL,
    MIN_SCAN_INTERVAL,
)
from .coordinator import CfosConfigEntry

_LOGGER = logging.getLogger(__name__)


def _whole_number(maximum: int) -> probatio.All[Any]:
    """A whole number from 1 to ``maximum``, typed into a box."""
    return probatio.All(
        NumberSelector(
            NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=maximum)
        ),
        probatio.Coerce(int),
    )


PORT_FIELD = _whole_number(65535)
UNIT_ID_FIELD = _whole_number(247)

CONNECTION_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_EVSE_PORT): PORT_FIELD,
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_EVSE_UNIT_ID): UNIT_ID_FIELD,
    }
)

SCAN_INTERVAL_SCHEMA = {
    probatio.Required(CONF_SCAN_INTERVAL, default=DEFAULT_SCAN_INTERVAL): probatio.All(
        NumberSelector(
            NumberSelectorConfig(
                mode=NumberSelectorMode.SLIDER,
                min=MIN_SCAN_INTERVAL,
                max=MAX_SCAN_INTERVAL,
                step=1,
                unit_of_measurement="s",
            )
        ),
        probatio.Coerce(int),
    ),
}

CHARGING_MANAGER_SCHEMA = {
    probatio.Required(CONF_CHARGING_MANAGER, default=False): BooleanSelector(),
    probatio.Required(
        CONF_CHARGING_MANAGER_PORT, default=DEFAULT_CHARGING_MANAGER_PORT
    ): PORT_FIELD,
    probatio.Required(
        CONF_CHARGING_MANAGER_UNIT_ID, default=DEFAULT_CHARGING_MANAGER_UNIT_ID
    ): UNIT_ID_FIELD,
}

STEP_USER_DATA_SCHEMA = CONNECTION_SCHEMA.extend(
    {**SCAN_INTERVAL_SCHEMA, **CHARGING_MANAGER_SCHEMA}
)

OPTIONS_SCHEMA = probatio.Schema(
    {
        **SCAN_INTERVAL_SCHEMA,
        probatio.Required(CONF_S0_METERS, default=[]): SelectSelector(
            SelectSelectorConfig(
                options=[str(number) for number in S0_METER_PORTS],
                multiple=True,
                translation_key=CONF_S0_METERS,
            )
        ),
        **CHARGING_MANAGER_SCHEMA,
    }
)


async def _async_identify_wallbox(
    hass: HomeAssistant,
    data: dict[str, Any],
    errors: dict[str, str],
    placeholders: dict[str, str],
) -> str | None:
    """Return the wallbox's serial number, or fill in the errors."""
    params = ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])
    try:
        async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
            wallbox = CfosWallbox(unit)
            await wallbox.async_ensure_setup()
    except UnsupportedDeviceError:
        errors["base"] = "not_cfos"
    except (ModbusError, HomeAssistantError) as err:
        errors["base"] = "cannot_connect"
        placeholders["error"] = str(err)
    except Exception:
        _LOGGER.exception("Unexpected error identifying the wallbox")
        errors["base"] = "unknown"
    else:
        if serial := wallbox.serial_number:
            return serial
        errors["base"] = "not_cfos"  # nothing to tell this controller apart by
    return None


async def _async_check_charging_manager(
    hass: HomeAssistant,
    host: str,
    options: dict[str, Any],
    errors: dict[str, str],
    placeholders: dict[str, str],
) -> None:
    """Make sure the Charging Manager answers if it is switched on, or fill in the errors."""
    if not options[CONF_CHARGING_MANAGER]:
        return
    params = ModbusTcpParams(host=host, port=options[CONF_CHARGING_MANAGER_PORT])
    unit_id = options[CONF_CHARGING_MANAGER_UNIT_ID]
    try:
        async with async_get_temporary_unit(hass, params, unit_id) as unit:
            await CfosChargingManager(unit).async_ensure_setup()
    except UnsupportedDeviceError:
        errors["base"] = "charging_manager_not_found"
    except (ModbusError, HomeAssistantError) as err:
        errors["base"] = "charging_manager_cannot_connect"
        placeholders["error"] = str(err)
    except Exception:
        _LOGGER.exception("Unexpected error looking for the Charging Manager")
        errors["base"] = "unknown"


class CfosPowerBrainConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the cFos Power Brain Wallbox."""

    VERSION = 1

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CfosConfigEntry) -> CfosOptionsFlow:
        """Create the options flow."""
        return CfosOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask for the wallbox, the polling interval and the Charging Manager."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            # How to reach the wallbox is data; the rest can change in the options.
            data = {
                key: user_input[key] for key in (CONF_HOST, CONF_PORT, CONF_UNIT_ID)
            }
            options = {
                key: value for key, value in user_input.items() if key not in data
            }
            serial = await _async_identify_wallbox(
                self.hass, data, errors, placeholders
            )
            if serial is not None:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates=data)
                await _async_check_charging_manager(
                    self.hass, data[CONF_HOST], options, errors, placeholders
                )
                if not errors:
                    return self.async_create_entry(
                        title=DEFAULT_NAME, data=data, options=options
                    )

        return self.async_show_form(
            step_id="user",
            data_schema=self.add_suggested_values_to_schema(
                STEP_USER_DATA_SCHEMA, user_input
            ),
            errors=errors,
            description_placeholders=placeholders,
        )

    async def async_step_reconfigure(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Change how the wallbox is reached, e.g. after a new IP address."""
        entry = self._get_reconfigure_entry()
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            serial = await _async_identify_wallbox(
                self.hass, user_input, errors, placeholders
            )
            if serial is not None:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_mismatch(reason="wrong_device")
                return self.async_update_reload_and_abort(entry, data=user_input)

        return self.async_show_form(
            step_id="reconfigure",
            data_schema=self.add_suggested_values_to_schema(
                CONNECTION_SCHEMA, user_input or entry.data
            ),
            errors=errors,
            description_placeholders=placeholders,
        )


class CfosOptionsFlow(OptionsFlowWithReload):
    """Polling interval, the S0 meters and the Charging Manager."""

    async def async_step_init(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Manage the options."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            await _async_check_charging_manager(
                self.hass,
                self.config_entry.data[CONF_HOST],
                user_input,
                errors,
                placeholders,
            )
            if not errors:
                return self.async_create_entry(data=user_input)

        return self.async_show_form(
            step_id="init",
            data_schema=self.add_suggested_values_to_schema(
                OPTIONS_SCHEMA, user_input or self.config_entry.options
            ),
            errors=errors,
            description_placeholders=placeholders,
        )
