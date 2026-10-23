"""The identity block every cFos Modbus device serves, registers 8000-8031."""

from __future__ import annotations

from modbus_connection.model import Component, integer, raw_register, string

from .const import VENDOR_ID


def _major_minor(word: int | None) -> str | None:
    """Format a word that packs major and minor version into its two bytes."""
    if word is None:
        return None
    return f"{word >> 8}.{word & 0xFF}"


class Identity(Component):
    """Who the device is. Read once at setup; it never changes while running."""

    register_ranges = ((8000, 8031),)

    _vendor_high = raw_register(8000)
    _vendor_low = raw_register(8001)

    product_id = integer(8002, signed=False)
    """Product id, 1 for the Power Brain."""

    device_id = integer(8003, signed=False)
    """Which device inside the product answers: EVSE or one of the S0 meters."""

    # The register map gives product_version two registers and product_build
    # the second of them, so read the version as one word packing major.minor
    # the way mapping_version does.
    _version = raw_register(8004)

    build = integer(8005, signed=False)
    """Product build number."""

    _mapping_version = raw_register(8006)

    serial_number = string(8008, 8)
    """Serial number of the controller."""

    name = string(8016, 16)
    """Product name, "cFos Power Brain Controller"."""

    @property
    def is_cfos(self) -> bool:
        """Whether the vendor id is cFos', in either word order."""
        return VENDOR_ID in (self._vendor_high, self._vendor_low)

    @property
    def firmware_version(self) -> str | None:
        """The product version, with the build number appended when known."""
        version = _major_minor(self._version)
        if version is None or not self.build:
            return version
        return f"{version}.{self.build}"

    @property
    def mapping_version(self) -> str | None:
        """Version of the register map the device implements."""
        return _major_minor(self._mapping_version)
