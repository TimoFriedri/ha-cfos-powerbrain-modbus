"""Buttons of the cFos Power Brain Wallbox."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any, override

from homeassistant.components.button import ButtonEntity, ButtonEntityDescription
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosDevice, CfosS0Meter, CfosWallbox
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CfosButtonEntityDescription[DeviceT: CfosDevice](
    ButtonEntityDescription, CfosEntityDescription
):
    """Describe an action on a cFos unit."""

    press_fn: Callable[[DeviceT], Awaitable[None]]


WALLBOX_BUTTONS: tuple[CfosButtonEntityDescription[CfosWallbox], ...] = (
    CfosButtonEntityDescription[CfosWallbox](
        key="wake_up_vehicle",
        translation_key="wake_up_vehicle",
        component="status",
        press_fn=lambda device: device.async_wake_up(),
    ),
)

S0_METER_BUTTONS: tuple[CfosButtonEntityDescription[CfosS0Meter], ...] = (
    CfosButtonEntityDescription[CfosS0Meter](
        key="reset_energy",
        translation_key="reset_energy",
        component="readings",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda device: device.async_reset_energy(),
    ),
    CfosButtonEntityDescription[CfosS0Meter](
        key="reset_pulses",
        translation_key="reset_pulses",
        component="readings",
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
        press_fn=lambda device: device.async_reset_pulses(),
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the buttons."""
    runtime_data = entry.runtime_data
    wallbox = runtime_data.wallbox
    entities: list[CfosButton[Any]] = [
        CfosButton(wallbox, description) for description in WALLBOX_BUTTONS
    ]
    for meter in runtime_data.s0_meters.values():
        entities.extend(
            CfosButton(meter, description) for description in S0_METER_BUTTONS
        )
    async_add_entities(entities)


class CfosButton[DeviceT: CfosDevice](CfosEntity[DeviceT], ButtonEntity):
    """An action on a cFos unit."""

    entity_description: CfosButtonEntityDescription[DeviceT]

    @override
    async def async_press(self) -> None:
        """Run the action."""
        await self._async_write(self.entity_description.press_fn(self.device))
