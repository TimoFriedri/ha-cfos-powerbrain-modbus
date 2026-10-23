"""Switches of the cFos Power Brain."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosChargingManager, CfosDevice
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 1

FLAG_COUNT = 32


@dataclass(frozen=True, kw_only=True)
class CfosSwitchEntityDescription(SwitchEntityDescription, CfosEntityDescription):
    """Describe an on/off value of a cFos unit."""

    field: str = ""
    """Attribute name of the field on the component; unused with ``value_fn``."""

    value_fn: Callable[[Any], Any] | None = None
    write_fn: Callable[[Any, bool], Awaitable[None]] | None = None
    """Read and write a value that is no plain component field."""

    flash: bool = False
    """The device stores the value in flash, so unchanged values are not written."""


WALLBOX_SWITCHES: tuple[CfosSwitchEntityDescription, ...] = (
    CfosSwitchEntityDescription(
        key="charging_enabled",
        translation_key="charging_enabled",
        component="status",
        field="charging_enabled",
    ),
    CfosSwitchEntityDescription(
        key="relay2",
        translation_key="relay2",
        component="status",
        field="relay2",
        exists_fn=lambda device: device.status.has_relay2,
    ),
    CfosSwitchEntityDescription(
        key="default_charging_enabled",
        translation_key="default_charging_enabled",
        component="settings",
        field="default_charging_enabled",
        flash=True,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)


def _flag_value(number: int) -> Callable[[CfosChargingManager], bool | None]:
    """Read flag ``number`` (1-32)."""

    def value(device: CfosChargingManager) -> bool | None:
        flags = device.flags
        if flags is None or number > len(flags.flags):
            return None
        on: bool | None = flags.flags[number - 1].on
        return on

    return value


def _flag_exists(number: int) -> Callable[[CfosChargingManager], bool]:
    """Whether the Charging Manager has flag ``number`` (1-32)."""

    def exists(device: CfosChargingManager) -> bool:
        return device.flags is not None and number <= len(device.flags.flags)

    return exists


def _flag_write(number: int) -> Callable[[CfosChargingManager, bool], Awaitable[None]]:
    """Write flag ``number`` (1-32)."""

    def write(device: CfosChargingManager, on: bool) -> Awaitable[None]:
        return device.async_set_flag(number, on)

    return write


CHARGING_MANAGER_SWITCHES: tuple[CfosSwitchEntityDescription, ...] = (
    CfosSwitchEntityDescription(
        key="load_management",
        translation_key="load_management",
        component="parameters",
        field="load_management",
        flash=True,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    CfosSwitchEntityDescription(
        key="imbalance_includes_consumers",
        translation_key="imbalance_includes_consumers",
        component="parameters",
        field="imbalance_includes_consumers",
        flash=True,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    *(
        CfosSwitchEntityDescription(
            key=f"flag_{number}",
            translation_key="flag",
            translation_placeholders={"number": str(number)},
            component="flags",
            value_fn=_flag_value(number),
            write_fn=_flag_write(number),
            exists_fn=_flag_exists(number),
            entity_registry_enabled_default=False,
        )
        for number in range(1, FLAG_COUNT + 1)
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    runtime_data = entry.runtime_data
    wallbox = runtime_data.wallbox
    entities: list[CfosSwitch[Any]] = [
        CfosSwitch(wallbox, description)
        for description in WALLBOX_SWITCHES
        if description.supported(wallbox.device)
    ]
    if (manager := runtime_data.charging_manager) is not None:
        entities.extend(
            CfosSwitch(manager, description)
            for description in CHARGING_MANAGER_SWITCHES
            if description.supported(manager.device)
        )
    async_add_entities(entities)


class CfosSwitch[DeviceT: CfosDevice](CfosEntity[DeviceT], SwitchEntity):
    """An on/off value of a cFos unit."""

    entity_description: CfosSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """The state from the most recent poll."""
        description = self.entity_description
        if description.value_fn is not None:
            value = description.value_fn(self.device)
        else:
            component = getattr(self.device, description.component)
            value = getattr(component, description.field)
        # Some devices keep the flag in a float register: 1.0 or 0.0.
        return None if value is None else bool(value)

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the value on."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the value off."""
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        description = self.entity_description
        if description.flash and value == self.is_on:
            return
        if description.write_fn is not None:
            await self._async_write(description.write_fn(self.device, value))
            return
        component = getattr(self.device, description.component)
        await self._async_write(component.write(description.field, value))
