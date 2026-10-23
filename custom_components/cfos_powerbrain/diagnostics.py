"""Diagnostics of the cFos Power Brain: the raw register maps."""

from __future__ import annotations

from typing import Any

from modbus_connection import ModbusError
from modbus_connection.model.sunspec import SunSpecError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .cfos_modbus import CfosChargingManager, PowerBrainUnit, UnsupportedDeviceError
from .coordinator import CfosConfigEntry, CfosUnitData

TO_REDACT = {CONF_HOST, "unique_id", "serial_number"}


async def _async_unit_diagnostics(unit: CfosUnitData[Any]) -> dict[str, Any]:
    """The poll outcome and the live raw registers of one unit."""
    result: dict[str, Any] = {}
    for name, coordinator in (
        ("readings", unit.readings),
        ("settings", unit.settings),
    ):
        report = coordinator.data
        result[name] = {
            "last_update_success": coordinator.last_update_success,
            "updated": sorted(report.updated) if report else [],
            "failed": (
                {key: str(err) for key, err in report.failed.items()} if report else {}
            ),
        }
    device = unit.device
    try:
        registers = await device.async_read_raw()
    except (ModbusError, SunSpecError, UnsupportedDeviceError) as err:
        result["registers"] = {"error": str(err)}
        return result
    # Redacted only now: the Charging Manager's serial is placed by the scan.
    holding = registers.get("holding", {})
    for address in device.private_registers:
        if address in holding:
            holding[address] = "**REDACTED**"
    result["firmware"] = device.firmware_version
    if isinstance(device, PowerBrainUnit):
        result["mapping_version"] = device.identity.mapping_version
    if isinstance(device, CfosChargingManager) and device.models is not None:
        result["models"] = [
            {"id": model.model_id, "address": model.address, "length": model.length}
            for model in device.models.chain
        ]
        result["variable_layout"] = (
            type(device.variables).__name__ if device.variables else None
        )
    result["registers"] = registers
    return result


async def async_get_config_entry_diagnostics(
    hass: HomeAssistant, entry: CfosConfigEntry
) -> dict[str, Any]:
    """Return diagnostics for a config entry."""
    runtime_data = entry.runtime_data
    return {
        "entry": async_redact_data(
            {"data": dict(entry.data), "options": dict(entry.options)}, TO_REDACT
        ),
        "wallbox": await _async_unit_diagnostics(runtime_data.wallbox),
        "s0_meters": {
            str(number): await _async_unit_diagnostics(meter)
            for number, meter in runtime_data.s0_meters.items()
        },
        "charging_manager": (
            await _async_unit_diagnostics(runtime_data.charging_manager)
            if runtime_data.charging_manager
            else None
        ),
    }
