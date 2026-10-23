"""Diagnostics of the cFos Power Brain: the raw register maps."""

from __future__ import annotations

from typing import Any

from modbus_connection import ModbusError

from homeassistant.components.diagnostics import async_redact_data
from homeassistant.const import CONF_HOST
from homeassistant.core import HomeAssistant

from .coordinator import CfosConfigEntry, CfosUnitData

TO_REDACT = {CONF_HOST, "unique_id", "serial_number"}

# Registers that identify the owner: the serial number and the last RFID tag.
PRIVATE_REGISTERS = (*range(8008, 8016), *range(8096, 8111))


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
    try:
        registers = await unit.device.async_read_raw()
    except ModbusError as err:
        result["registers"] = {"error": str(err)}
        return result
    holding = registers.get("holding", {})
    for address in PRIVATE_REGISTERS:
        if address in holding:
            holding[address] = "**REDACTED**"
    result["firmware"] = unit.device.identity.firmware_version
    result["mapping_version"] = unit.device.identity.mapping_version
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
    }
