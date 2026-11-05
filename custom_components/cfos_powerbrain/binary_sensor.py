"""Binary sensors of the cFos Power Brain Wallbox."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from typing import override

from homeassistant.components.binary_sensor import (
    BinarySensorDeviceClass,
    BinarySensorEntity,
    BinarySensorEntityDescription,
)
from homeassistant.const import EntityCategory
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosWallbox, EvseStatus
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription, supported_entities

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CfosBinarySensorEntityDescription(
    BinarySensorEntityDescription, CfosEntityDescription
):
    """Describe a binary sensor of the wallbox."""

    value_fn: Callable[[EvseStatus], bool | None]


WALLBOX_BINARY_SENSORS: tuple[CfosBinarySensorEntityDescription, ...] = (
    CfosBinarySensorEntityDescription(
        key="vehicle_connected",
        translation_key="vehicle_connected",
        component="status",
        device_class=BinarySensorDeviceClass.PLUG,
        value_fn=lambda status: status.vehicle_connected,
    ),
    CfosBinarySensorEntityDescription(
        key="charging",
        component="status",
        device_class=BinarySensorDeviceClass.BATTERY_CHARGING,
        value_fn=lambda status: status.charging,
    ),
    CfosBinarySensorEntityDescription(
        key="problem",
        component="status",
        device_class=BinarySensorDeviceClass.PROBLEM,
        value_fn=lambda status: status.problem,
    ),
    CfosBinarySensorEntityDescription(
        key="phase_switching_allowed",
        translation_key="phase_switching_allowed",
        component="status",
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda status: status.phase_switching_allowed,
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the binary sensors."""
    async_add_entities(
        supported_entities(
            entry.runtime_data.wallbox, WALLBOX_BINARY_SENSORS, CfosBinarySensor
        )
    )


class CfosBinarySensor(CfosEntity[CfosWallbox], BinarySensorEntity):
    """A binary sensor of the wallbox."""

    entity_description: CfosBinarySensorEntityDescription

    @property
    @override
    def is_on(self) -> bool | None:
        """The state from the most recent poll."""
        return self.entity_description.value_fn(self._component)
