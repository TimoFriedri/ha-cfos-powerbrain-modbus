"""Select entities of the cFos Power Brain Wallbox."""

from __future__ import annotations

from dataclasses import dataclass

from homeassistant.components.select import SelectEntity, SelectEntityDescription
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import CfosWallbox, PhaseRelay
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CfosSelectEntityDescription(SelectEntityDescription, CfosEntityDescription):
    """Describe a select of the wallbox."""


PHASE_MODE = CfosSelectEntityDescription(
    key="phase_mode",
    translation_key="phase_mode",
    component="status",
    options=[relay.name.lower() for relay in PhaseRelay],
    exists_fn=lambda status: status.phase_switching_allowed,
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the phase mode select, for wallboxes that can switch phases."""
    wallbox = entry.runtime_data.wallbox
    if PHASE_MODE.supported(wallbox.device):
        async_add_entities([CfosPhaseModeSelect(wallbox, PHASE_MODE)])


class CfosPhaseModeSelect(CfosEntity[CfosWallbox], SelectEntity):
    """Charge on one or three phases."""

    entity_description: CfosSelectEntityDescription

    @property
    def current_option(self) -> str | None:
        """The contactor in use."""
        relay = self.device.status.phase_relay
        return None if relay is None else relay.name.lower()

    async def async_select_option(self, option: str) -> None:
        """Switch the contactor."""
        await self._async_write(
            self.device.async_set_phase_relay(PhaseRelay[option.upper()])
        )
