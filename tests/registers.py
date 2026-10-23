"""Register images of a cFos Power Brain, for the in-memory mock backend."""

from __future__ import annotations

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
