"""Polling of the cFos Power Brain Wallbox's Modbus units."""

from __future__ import annotations

from collections.abc import Awaitable, Callable
from dataclasses import dataclass, field
from datetime import timedelta
import logging
from typing import override

from modbus_connection import ModbusError
from modbus_connection.model import UpdateReport
from modbus_connection.model.sunspec import SunSpecError, SunSpecMapShiftError

from homeassistant.config_entries import ConfigEntry
from homeassistant.core import HomeAssistant
from homeassistant.exceptions import ConfigEntryError
from homeassistant.helpers.device_registry import DeviceInfo
from homeassistant.helpers.update_coordinator import DataUpdateCoordinator, UpdateFailed

from .cfos_modbus import (
    CfosChargingManager,
    CfosDevice,
    CfosS0Meter,
    CfosWallbox,
    UnsupportedDeviceError,
)
from .const import DOMAIN

_LOGGER = logging.getLogger(__name__)

type CfosConfigEntry = ConfigEntry[CfosRuntimeData]


class CfosCoordinator(DataUpdateCoordinator[UpdateReport]):
    """Run one of a device's update methods on its own interval."""

    config_entry: CfosConfigEntry

    def __init__(
        self,
        hass: HomeAssistant,
        entry: CfosConfigEntry,
        poll: Callable[[], Awaitable[UpdateReport]],
        interval: timedelta,
        name: str,
        *,
        optional: bool = False,
    ) -> None:
        """Initialize the coordinator.

        An ``optional`` device, like the Charging Manager, leaves its entities
        unavailable when it cannot be used instead of failing the entry.
        """
        super().__init__(
            hass,
            _LOGGER,
            config_entry=entry,
            name=name,
            update_interval=interval,
        )
        self._poll = poll
        self._optional = optional
        self._failing: set[str] = set()

    @override
    async def _async_update_data(self) -> UpdateReport:
        """Poll the device and report which components refreshed."""
        try:
            report = await self._poll()
        except UnsupportedDeviceError as err:
            if self._optional:
                raise UpdateFailed(
                    translation_domain=DOMAIN,
                    translation_key="charging_manager_unavailable",
                    translation_placeholders={"error": str(err)},
                ) from err
            raise ConfigEntryError(
                translation_domain=DOMAIN, translation_key="unsupported_device"
            ) from err
        except SunSpecMapShiftError as err:
            # A firmware update moved the models: set up again to rescan them.
            self.hass.config_entries.async_schedule_reload(self.config_entry.entry_id)
            raise UpdateFailed(
                translation_domain=DOMAIN, translation_key="models_moved"
            ) from err
        except (ModbusError, SunSpecError) as err:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="communication_error",
                translation_placeholders={"error": str(err)},
            ) from err
        if report.failed and not report.updated:
            raise UpdateFailed(
                translation_domain=DOMAIN,
                translation_key="no_component_answered",
            ) from ExceptionGroup(
                "every component failed to refresh", list(report.failed.values())
            )
        self._log_component_changes(report)
        return report

    def _log_component_changes(self, report: UpdateReport) -> None:
        """Log a component's first failure and its recovery, once each."""
        for name, cause in report.failed.items():
            if name not in self._failing:
                self._failing.add(name)
                _LOGGER.info(
                    "%s: %s failed to refresh, its entities are unavailable: %s",
                    self.name,
                    name,
                    cause,
                )
        for name in report.updated & self._failing:
            self._failing.discard(name)
            _LOGGER.info("%s: %s is available again", self.name, name)


@dataclass
class CfosUnitData[DeviceT: CfosDevice]:
    """One Modbus unit of the controller and the coordinators polling it."""

    device: DeviceT
    readings: CfosCoordinator
    settings: CfosCoordinator
    device_info: DeviceInfo
    unique_id_prefix: str

    def coordinator_for(self, component: str) -> CfosCoordinator:
        """The coordinator that polls a component."""
        if component in self.device.READINGS:
            return self.readings
        return self.settings


@dataclass
class CfosRuntimeData:
    """Everything a loaded config entry holds."""

    wallbox: CfosUnitData[CfosWallbox]
    s0_meters: dict[int, CfosUnitData[CfosS0Meter]] = field(default_factory=dict)
    charging_manager: CfosUnitData[CfosChargingManager] | None = None
