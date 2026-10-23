# /// script
# requires-python = ">=3.12"
# dependencies = ["modbus-connection[tmodbus]>=4.12.3"]
# ///
"""Read a cFos Power Brain Wallbox over Modbus TCP and print what the integration sees.

Needs only Python 3.12+ and modbus-connection, no Home Assistant. uv installs
them from the header above:

    uv run script/dump_registers.py 192.168.1.50
    uv run script/dump_registers.py 192.168.1.50 --s0 1 --raw
    uv run script/dump_registers.py 192.168.1.50 --charging-manager --raw

Without uv, run ``pip install "modbus-connection[tmodbus]>=4.12.3"`` first and
start the script with ``python`` instead of ``uv run``.

The cFos Charging Manager is read through its SunSpec server, which has to be
switched on under "SunSpec address settings" in its configuration.

Attach the output to an issue when a value looks wrong. It contains the serial
numbers and the last RFID tag; remove them first if you like.
"""

from __future__ import annotations

import argparse
import asyncio
import json
from pathlib import Path
import sys
from typing import Any

from modbus_connection import ModbusTcpParams
from modbus_connection.tmodbus import ModbusConnection

# The device library is vendored inside the integration; import it on its own
# so Home Assistant does not need to be installed.
sys.path.insert(
    0, str(Path(__file__).parents[1] / "custom_components" / "cfos_powerbrain")
)

from cfos_modbus import (
    DEFAULT_CHARGING_MANAGER_PORT,
    DEFAULT_CHARGING_MANAGER_UNIT_ID,
    DEFAULT_EVSE_PORT,
    DEFAULT_EVSE_UNIT_ID,
    S0_METER_PORTS,
    S0_METER_UNIT_IDS,
    CfosChargingManager,
    CfosDevice,
    CfosS0Meter,
    CfosWallbox,
    PowerBrainUnit,
)


def _fields(component: Any) -> dict[str, Any]:
    """The decoded values of a component, keyed by field name."""
    if component is None:
        return {}
    return {name: getattr(component, name) for name in type(component).declared_fields}


async def _dump(device: CfosDevice, *, raw: bool) -> dict[str, Any]:
    report = await device.async_update()
    result: dict[str, Any] = {
        "updated": sorted(report.updated),
        "failed": {name: str(err) for name, err in report.failed.items()},
        "firmware": device.firmware_version,
    }
    if isinstance(device, PowerBrainUnit):
        result["mapping_version"] = device.identity.mapping_version
    if isinstance(device, CfosChargingManager) and device.models is not None:
        result["models"] = [
            {"id": model.model_id, "address": model.address, "length": model.length}
            for model in device.models.chain
        ]
        result["variable_names"] = device.variable_names
    for name in (*device.IDENTITY, *device.READINGS, *device.SETTINGS):
        result[name] = _fields(getattr(device, name))
    if raw:
        result["raw"] = await device.async_read_raw()
    return result


async def main() -> None:
    """Dump the wallbox and the requested S0 meters as JSON."""
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("host", help="IP address or host name of the wallbox")
    parser.add_argument("--port", type=int, default=DEFAULT_EVSE_PORT)
    parser.add_argument("--unit-id", type=int, default=DEFAULT_EVSE_UNIT_ID)
    parser.add_argument(
        "--s0", type=int, choices=sorted(S0_METER_PORTS), action="append", default=[]
    )
    parser.add_argument(
        "--charging-manager", action="store_true", help="read the Charging Manager"
    )
    parser.add_argument("--cm-port", type=int, default=DEFAULT_CHARGING_MANAGER_PORT)
    parser.add_argument(
        "--cm-unit-id", type=int, default=DEFAULT_CHARGING_MANAGER_UNIT_ID
    )
    parser.add_argument("--raw", action="store_true", help="include raw registers")
    args = parser.parse_args()

    output: dict[str, Any] = {}
    targets: list[tuple[str, int, int, type[CfosDevice]]] = [
        ("wallbox", args.port, args.unit_id, CfosWallbox)
    ]
    targets += [
        (f"s0_meter_{n}", S0_METER_PORTS[n], S0_METER_UNIT_IDS[n], CfosS0Meter)
        for n in args.s0
    ]
    if args.charging_manager:
        targets.append(
            ("charging_manager", args.cm_port, args.cm_unit_id, CfosChargingManager)
        )
    for name, port, unit_id, device_type in targets:
        connection = ModbusConnection(ModbusTcpParams(host=args.host, port=port))
        try:
            output[name] = await _dump(
                device_type(connection.for_unit(unit_id)), raw=args.raw
            )
        except Exception as err:  # report every failure in the dump
            output[name] = {"error": f"{type(err).__name__}: {err}"}
        finally:
            await connection.close()

    print(json.dumps(output, indent=2, default=str))


if __name__ == "__main__":
    asyncio.run(main())
