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

CONNECTION_SCHEMA = probatio.Schema(
    {
        probatio.Required(CONF_HOST): TextSelector(),
        probatio.Required(CONF_PORT, default=DEFAULT_EVSE_PORT): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(CONF_UNIT_ID, default=DEFAULT_EVSE_UNIT_ID): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)
            ),
            probatio.Coerce(int),
        ),
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

STEP_USER_DATA_SCHEMA = CONNECTION_SCHEMA.extend(SCAN_INTERVAL_SCHEMA)


async def _async_probe(hass: HomeAssistant, data: dict[str, Any]) -> str:
    """Identify the wallbox and return its serial number, or raise."""
    params = ModbusTcpParams(host=data[CONF_HOST], port=data[CONF_PORT])
    async with async_get_temporary_unit(hass, params, data[CONF_UNIT_ID]) as unit:
        wallbox = CfosWallbox(unit)
        await wallbox.async_ensure_setup()
    serial = wallbox.serial_number
    if not serial:
        raise UnsupportedDeviceError("The wallbox reports no serial number")
    return serial


class CfosPowerBrainConfigFlow(ConfigFlow, domain=DOMAIN):
    """Handle a config flow for the cFos Power Brain Wallbox."""

    VERSION = 1
    MINOR_VERSION = 2

    @staticmethod
    @callback
    def async_get_options_flow(config_entry: CfosConfigEntry) -> CfosOptionsFlow:
        """Create the options flow."""
        return CfosOptionsFlow()

    async def async_step_user(
        self, user_input: dict[str, Any] | None = None
    ) -> ConfigFlowResult:
        """Ask where the wallbox is and how often to poll it, then identify it."""
        errors: dict[str, str] = {}
        placeholders: dict[str, str] = {}
        if user_input is not None:
            # How to reach the wallbox is data; the interval stays an option.
            options = {CONF_SCAN_INTERVAL: user_input[CONF_SCAN_INTERVAL]}
            data = {
                key: value
                for key, value in user_input.items()
                if key != CONF_SCAN_INTERVAL
            }
            serial = await self._async_validate(data, errors, placeholders)
            if serial is not None:
                await self.async_set_unique_id(serial)
                self._abort_if_unique_id_configured(updates=data)
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
            serial = await self._async_validate(user_input, errors, placeholders)
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

    async def _async_validate(
        self,
        data: dict[str, Any],
        errors: dict[str, str],
        placeholders: dict[str, str],
    ) -> str | None:
        """Probe the wallbox; return its serial, or fill in the errors."""
        try:
            return await _async_probe(self.hass, data)
        except UnsupportedDeviceError:
            errors["base"] = "not_cfos"
        except (ModbusError, HomeAssistantError) as err:
            errors["base"] = "cannot_connect"
            placeholders["error"] = str(err)
        except Exception:
            _LOGGER.exception("Unexpected error identifying the wallbox")
            errors["base"] = "unknown"
        return None


async def _async_probe_charging_manager(
    hass: HomeAssistant, host: str, port: int, unit_id: int
) -> None:
    """Find the Charging Manager's SunSpec server, or raise."""
    params = ModbusTcpParams(host=host, port=port)
    async with async_get_temporary_unit(hass, params, unit_id) as unit:
        await CfosChargingManager(unit).async_ensure_setup()


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
        probatio.Required(CONF_CHARGING_MANAGER, default=False): BooleanSelector(),
        probatio.Required(
            CONF_CHARGING_MANAGER_PORT, default=DEFAULT_CHARGING_MANAGER_PORT
        ): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=65535)
            ),
            probatio.Coerce(int),
        ),
        probatio.Required(
            CONF_CHARGING_MANAGER_UNIT_ID, default=DEFAULT_CHARGING_MANAGER_UNIT_ID
        ): probatio.All(
            NumberSelector(
                NumberSelectorConfig(mode=NumberSelectorMode.BOX, min=1, max=247)
            ),
            probatio.Coerce(int),
        ),
    }
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
            if user_input[CONF_CHARGING_MANAGER]:
                try:
                    await _async_probe_charging_manager(
                        self.hass,
                        self.config_entry.data[CONF_HOST],
                        user_input[CONF_CHARGING_MANAGER_PORT],
                        user_input[CONF_CHARGING_MANAGER_UNIT_ID],
                    )
                except UnsupportedDeviceError:
                    errors["base"] = "charging_manager_not_found"
                except (ModbusError, HomeAssistantError) as err:
                    errors["base"] = "charging_manager_cannot_connect"
                    placeholders["error"] = str(err)
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
