"""Register images of a cFos Power Brain, for the in-memory mock backend."""

from __future__ import annotations

import struct

SERIAL = "PB2X123456"


def ascii_words(text: str, length: int) -> list[int]:
    """Pack ASCII into ``length`` registers, two characters each (hi, lo)."""
    padded = text.ljust(length * 2, "\0")[: length * 2]
    return [(ord(padded[i]) << 8) | ord(padded[i + 1]) for i in range(0, length * 2, 2)]


def words(value: int, count: int) -> list[int]:
    """Split a non-negative or two's-complement value into big-endian words."""
    value &= (1 << (16 * count)) - 1
    return [(value >> (16 * (count - 1 - i))) & 0xFFFF for i in range(count)]


def identity(device_id: int = 0x100) -> dict[int, int | list[int]]:
    """The identity block every unit serves."""
    return {
        8000: [0, 0xCF05],
        8002: 1,
        8003: device_id,
        8004: 0x0119,  # 1.25
        8005: 3,
        8006: 0x0102,
        8008: ascii_words(SERIAL, 8),
        8016: ascii_words("cFos Power Brain Controller", 16),
        8040: 1,
    }


def wallbox(
    *, has_meter: bool = True, s0_inputs: int = 0x0100
) -> dict[int, int | list[int]]:
    """A charging three-phase wallbox with an attached meter."""
    registers: dict[int, int | list[int]] = {
        **identity(),
        # settings
        8080: 0,
        8081: 160,
        8082: 1,
        8083: words(300, 2),
        8085: 60,
        # status
        8086: 0,
        8087: 0,
        8088: 0,
        8090: 320,
        8091: 0,
        8092: 2,
        8093: 160,
        8094: 1,
        8095: 160,
        8096: ascii_words("04A1B2C3D4", 15),
        8111: 1,
        8112: int(has_meter),
        8113: s0_inputs,
        # health
        8120: words(12, 2),
        8122: 35,
    }
    if has_meter:
        registers |= {
            8057: 1,
            8058: words(1_234_567, 4),
            8062: words(7360, 2),
            8064: words(107, 2),
            8066: words(106, 2),
            8068: words(108, 2),
        }
    return registers


def s0_meter(device_id: int = 0x101) -> dict[int, int | list[int]]:
    """An S0 meter input counting a heat pump."""
    return {
        **identity(device_id),
        8042: words(1000, 2),
        8044: 0b111,
        8045: 230,
        8046: 230,
        8047: 230,
        8050: words(5_000_000, 4),
        8054: words(1200, 2),
        8056: 0,
        8057: 1,
        8058: words(5_000_000, 4),
        8062: words(3000, 2),
        8064: words(43, 2),
        8066: words(43, 2),
        8068: words(43, 2),
    }


# The Charging Manager's SunSpec server.

CM_SERIAL = "CM2X654321"
CM_METER_POWER = {
    "grid": 2500.0,
    "consumers": 9800.0,
    "generators": 7300.0,
    "pv_surplus": 0.0,
    "wallbox_used": 7360.0,
    "wallbox_available": 11040.0,
    "fault": 0.0,
}


def float_words(value: float) -> list[int]:
    """An IEEE-754 single over two big-endian registers."""
    (raw,) = struct.unpack(">I", struct.pack(">f", value))
    return [raw >> 16, raw & 0xFFFF]


def _meter(power: float) -> list[int]:
    """Model 213 data (124 registers) for a meter drawing ``power``."""
    data = [0xFFFF] * 124  # unimplemented points read NaN
    values = {
        2: power / 230 / 3 * 3,
        4: power / 230 / 3,
        6: power / 230 / 3,
        8: power / 230 / 3,
        12: 230.0,
        14: 231.0,
        16: 229.0,
        26: 50.0,
        28: power,
        30: power / 3,
        32: power / 3,
        34: power / 3,
        60: 1000.0,
        68: 250000.0,
    }
    for offset, value in values.items():
        data[offset - 2 : offset] = float_words(value)
    return data


def charging_manager(
    *, variables: tuple[str, ...] = ("pv_mode", "night_rate"), name_registers: int = 20
) -> dict[int, int | list[int]]:
    """The SunSpec map of a Charging Manager, laid out as cFos documents it.

    ``name_registers`` picks the variable layout: 20 (as the text describes)
    or 21 (as the register table shows).
    """
    words: list[int] = [0x5375, 0x6E53]  # "SunS"
    common = (
        ascii_words("cFos", 16)
        + ascii_words("Charging Manager", 16)
        + ascii_words("", 8)
        + ascii_words("2.1.4", 8)
        + ascii_words(CM_SERIAL, 16)
        + [1, 0x8000]
    )
    words += [1, len(common), *common]
    for power in CM_METER_POWER.values():
        words += [213, 124, *_meter(power)]
    parameters: list[int] = []
    for value in (63000.0, 2000.0, 1000.0, 32000.0, 20000.0, 1.0, 0.0, 100.0):
        parameters += float_words(value)
    words += [60000, len(parameters), *parameters]
    flags = [0] * 32
    flags[2] = 1  # CM._flag3 is set
    words += [60001, len(flags), *flags]
    block: list[int] = []
    for index, name in enumerate(variables):
        block += ascii_words(name, name_registers) + float_words(float(index + 1))
    words += [60002, len(block), *block]
    words += [0xFFFF, 0]
    return {40000: words}
