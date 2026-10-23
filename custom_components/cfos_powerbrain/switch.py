"""Switches of the cFos Power Brain."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.switch import SwitchEntity, SwitchEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosWallbox
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CfosSwitchEntityDescription(SwitchEntityDescription, CfosEntityDescription):
    """Describe a 0/1 register of the wallbox."""

    field: str
    """Attribute name of the field on the component."""

    flash: bool = False
    """The device stores the register in flash, so unchanged values are not written."""


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


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the switches."""
    wallbox = entry.runtime_data.wallbox
    async_add_entities(
        CfosSwitch(wallbox, description)
        for description in WALLBOX_SWITCHES
        if description.supported(wallbox.device)
    )


class CfosSwitch(CfosEntity[CfosWallbox], SwitchEntity):
    """A 0/1 register of the wallbox."""

    entity_description: CfosSwitchEntityDescription

    @property
    def is_on(self) -> bool | None:
        """The state from the most recent poll."""
        component = getattr(self.device, self.entity_description.component)
        value: bool | None = getattr(component, self.entity_description.field)
        return value

    async def async_turn_on(self, **kwargs: Any) -> None:
        """Set the register to 1."""
        await self._async_set(True)

    async def async_turn_off(self, **kwargs: Any) -> None:
        """Set the register to 0."""
        await self._async_set(False)

    async def _async_set(self, value: bool) -> None:
        description = self.entity_description
        if description.flash and value == self.is_on:
            return
        component = getattr(self.device, description.component)
        await self._async_write(component.write(description.field, value))
