"""Base entity for the cFos Power Brain Wallbox."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass
from typing import Any

from modbus_connection import ModbusError

from homeassistant.exceptions import HomeAssistantError
from homeassistant.helpers.entity import EntityDescription
from homeassistant.helpers.update_coordinator import CoordinatorEntity

from .cfos_modbus import CfosDevice
from .const import DOMAIN
from .coordinator import CfosCoordinator, CfosUnitData


@dataclass(frozen=True, kw_only=True)
class CfosEntityDescription(EntityDescription):
    """Describe an entity backed by one component of a cFos unit."""

    component: str
    """Attribute name of the component on the device, e.g. ``status``."""

    exists_fn: Callable[[Any], bool] | None = None
    """Whether the device has what the entity controls, settled at setup."""

    def supported(self, device: CfosDevice) -> bool:
        """Whether to create the entity for this device."""
        if getattr(device, self.component) is None:
            return False
        return self.exists_fn is None or self.exists_fn(device)


class CfosEntity[DeviceT: CfosDevice](CoordinatorEntity[CfosCoordinator]):
    """An entity of one cFos Modbus unit."""

    _attr_has_entity_name = True
    entity_description: CfosEntityDescription

    def __init__(
        self, unit: CfosUnitData[DeviceT], description: CfosEntityDescription
    ) -> None:
        """Initialize the entity."""
        super().__init__(unit.coordinator_for(description.component))
        self.entity_description = description
        self.device: DeviceT = unit.device
        self._attr_unique_id = f"{unit.unique_id_prefix}_{description.key}"
        self._attr_device_info = unit.device_info

    @property
    def available(self) -> bool:
        """Whether this entity's component answered the most recent poll."""
        if not super().available or self.coordinator.data is None:
            return False
        return self.entity_description.component not in self.coordinator.data.failed

    async def _async_write(self, write: Awaitable[None]) -> None:
        """Run a write, report a failure in the UI, then read the device back.

        The read-back is immediate rather than debounced, so a control shows
        what the device accepted even when several writes follow each other.
        """
        try:
            await write
        except ValueError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="invalid_value",
                translation_placeholders={"error": str(err)},
            ) from err
        except ModbusError as err:
            raise HomeAssistantError(
                translation_domain=DOMAIN,
                translation_key="write_failed",
                translation_placeholders={"error": str(err)},
            ) from err
        await self.coordinator.async_refresh()
