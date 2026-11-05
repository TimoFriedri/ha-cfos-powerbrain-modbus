"""Switches of the cFos Power Brain Wallbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosChargingManager, CfosDevice, CmFlag
from .coordinator import CfosConfigEntry, CfosUnitData
from .entity import CfosFieldEntity, CfosFieldEntityDescription, supported_entities

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CfosSwitchEntityDescription(SwitchEntityDescription, CfosFieldEntityDescription):
    """Describe an on/off value of a cFos unit."""


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
        exists_fn=lambda status: status.has_relay2,
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
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    runtime_data = entry.runtime_data
    entities: list[CfosSwitch[Any]] = []
    entities += supported_entities(runtime_data.wallbox, WALLBOX_SWITCHES, CfosSwitch)
    if (manager := runtime_data.charging_manager) is not None:
        entities += supported_entities(manager, CHARGING_MANAGER_SWITCHES, CfosSwitch)
        if (flags := manager.device.flags) is not None:
            entities.extend(
                CfosFlagSwitch(manager, number)
                for number in range(1, len(flags.flags) + 1)
            )
    async_add_entities(entities)


class CfosSwitch[DeviceT: CfosDevice](CfosFieldEntity[DeviceT], SwitchEntity):
    """An on/off value of a cFos unit."""

    entity_description: CfosSwitchEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """The state from the most recent poll."""
        value = self._field_value
        # Some devices keep the flag in a float register: 1.0 or 0.0.
        return None if value is None else bool(value)

    @override
    async def async_turn_on(self, **kwargs: Any) -> None:
        """Switch the value on."""
        await self._async_write_field(True)

    @override
    async def async_turn_off(self, **kwargs: Any) -> None:
        """Switch the value off."""
        await self._async_write_field(False)


class CfosFlagSwitch(CfosSwitch[CfosChargingManager]):
    """A Charging Manager flag, ``CM._flagN`` in formulas.

    Not saved by the Charging Manager, so it may be switched as often as needed.
    """

    def __init__(self, unit: CfosUnitData[CfosChargingManager], number: int) -> None:
        """Initialize the switch for flag ``number``, counted from 1."""
        super().__init__(
            unit,
            CfosSwitchEntityDescription(
                key=f"flag_{number}",
                translation_key="flag",
                translation_placeholders={"number": str(number)},
                component="flags",
                field="on",
                entity_registry_enabled_default=False,
            ),
        )
        self._index = number - 1

    @property
    @override
    def _component(self) -> CmFlag | None:
        """The flag itself, within the flags model."""
        flags = self.device.flags
        return None if flags is None else flags.flags[self._index]
