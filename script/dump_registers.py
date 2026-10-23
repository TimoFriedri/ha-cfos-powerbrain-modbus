"""Read a cFos Power Brain over Modbus TCP and print what the integration sees.

Needs only Python 3.12+ and modbus-connection, no Home Assistant:

    pip install "modbus-connection[tmodbus]>=4.12.3"
    python script/dump_registers.py 192.168.1.50
    python script/dump_registers.py 192.168.1.50 --s0 1 --raw

Attach the output to an issue when a value looks wrong. It contains the serial
number and the last RFID tag; remove them first if you like.
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
    DEFAULT_EVSE_PORT,
    DEFAULT_EVSE_UNIT_ID,
    S0_METER_PORTS,
    S0_METER_UNIT_IDS,
    CfosDevice,
    CfosS0Meter,
    CfosWallbox,
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
        "firmware": device.identity.firmware_version,
        "mapping_version": device.identity.mapping_version,
    }
    for name in ("identity", *device.READINGS, *device.SETTINGS):
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
