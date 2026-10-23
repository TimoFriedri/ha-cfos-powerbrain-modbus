"""Number entities of the cFos Power Brain Wallbox."""

from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from homeassistant.components.number import (
    NumberDeviceClass,
    NumberEntity,
    NumberEntityDescription,
    NumberMode,
)
from homeassistant.const import (
    PERCENTAGE,
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfElectricPotential,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from .cfos_modbus import MIN_CHARGING_CURRENT, CfosDevice
from .const import MAX_CURRENT_SETTING
from .coordinator import CfosConfigEntry
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 1


@dataclass(frozen=True, kw_only=True)
class CfosNumberEntityDescription(NumberEntityDescription, CfosEntityDescription):
    """Describe a writable register of a cFos unit."""

    field: str
    """Attribute name of the field on the component."""

    flash: bool = False
    """The device stores the register in flash, so unchanged values are not written."""


def _current(
    key: str,
    component: str,
    *,
    minimum: float = 0,
    setting: bool = False,
    flash: bool = False,
) -> CfosNumberEntityDescription:
    """Describe a current in steps of 0.1 A.

    A ``setting`` is configuration few need, hidden until enabled.
    """
    return CfosNumberEntityDescription(
        key=key,
        translation_key=key,
        component=component,
        field=key,
        flash=flash,
        device_class=NumberDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        native_min_value=minimum,
        native_max_value=MAX_CURRENT_SETTING,
        native_step=0.1,
        entity_category=EntityCategory.CONFIG if setting else None,
        entity_registry_enabled_default=not setting,
    )


WALLBOX_NUMBERS: tuple[CfosNumberEntityDescription, ...] = (
    _current("charging_current_limit", "status", minimum=MIN_CHARGING_CURRENT),
    _current("fixed_current", "status", setting=True),
    _current(
        "default_charging_current_limit",
        "settings",
        minimum=MIN_CHARGING_CURRENT,
        setting=True,
        flash=True,
    ),
    _current("default_fixed_current", "settings", setting=True, flash=True),
    _current("fail_safe_current", "settings", setting=True, flash=True),
    CfosNumberEntityDescription(
        key="fail_safe_duration",
        translation_key="fail_safe_duration",
        component="settings",
        field="fail_safe_duration",
        flash=True,
        device_class=NumberDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.SECONDS,
        native_min_value=0,
        native_max_value=86400,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
)

S0_METER_NUMBERS: tuple[CfosNumberEntityDescription, ...] = (
    CfosNumberEntityDescription(
        key="pulses_per_kwh",
        translation_key="pulses_per_kwh",
        component="settings",
        field="pulses_per_kwh",
        flash=True,
        native_min_value=1,
        native_max_value=100_000,
        native_step=1,
        mode=NumberMode.BOX,
        entity_category=EntityCategory.CONFIG,
        entity_registry_enabled_default=False,
    ),
    *(
        CfosNumberEntityDescription(
            key=f"nominal_voltage_l{phase}",
            translation_key="nominal_voltage",
            translation_placeholders={"phase": f"L{phase}"},
            component="settings",
            field=f"nominal_voltage_l{phase}",
            flash=True,
            device_class=NumberDeviceClass.VOLTAGE,
            native_unit_of_measurement=UnitOfElectricPotential.VOLT,
            native_min_value=100,
            native_max_value=280,
            native_step=1,
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        )
        for phase in (1, 2, 3)
    ),
)


CHARGING_MANAGER_CURRENT_LIMIT = 250.0
"""Highest current offered for a Charging Manager parameter in the UI, in A."""

CHARGING_MANAGER_NUMBERS: tuple[CfosNumberEntityDescription, ...] = (
    CfosNumberEntityDescription(
        key="max_total_current_percent",
        translation_key="max_total_current_percent",
        component="limit",
        field="max_total_current_percent",
        native_unit_of_measurement=PERCENTAGE,
        native_min_value=0,
        native_max_value=100,
        native_step=1,
    ),
    *(
        CfosNumberEntityDescription(
            key=field,
            translation_key=field,
            component="parameters",
            field=field,
            flash=True,
            device_class=NumberDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            native_min_value=0,
            native_max_value=CHARGING_MANAGER_CURRENT_LIMIT,
            native_step=0.1,
            mode=NumberMode.BOX,
            entity_category=EntityCategory.CONFIG,
            entity_registry_enabled_default=False,
        )
        for field in (
            "max_total_current",
            "power_reserve",
            "overdraw",
            "max_wallbox_current",
            "max_phase_imbalance",
        )
    ),
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the number entities."""
    runtime_data = entry.runtime_data
    wallbox = runtime_data.wallbox
    entities: list[CfosNumber[Any]] = [
        CfosNumber(wallbox, description)
        for description in WALLBOX_NUMBERS
        if description.supported(wallbox.device)
    ]
    for meter in runtime_data.s0_meters.values():
        entities.extend(
            CfosNumber(meter, description)
            for description in S0_METER_NUMBERS
            if description.supported(meter.device)
        )
    if (manager := runtime_data.charging_manager) is not None:
        entities.extend(
            CfosNumber(manager, description)
            for description in CHARGING_MANAGER_NUMBERS
            if description.supported(manager.device)
        )
    async_add_entities(entities)


class CfosNumber[DeviceT: CfosDevice](CfosEntity[DeviceT], NumberEntity):
    """A writable register of a cFos unit."""

    entity_description: CfosNumberEntityDescription

    @property
    def native_value(self) -> float | None:
        """The value from the most recent poll."""
        component = getattr(self.device, self.entity_description.component)
        value: float | None = getattr(component, self.entity_description.field)
        return value

    async def async_set_native_value(self, value: float) -> None:
        """Write the value to the device."""
        description = self.entity_description
        if description.flash and value == self.native_value:
            return
        component = getattr(self.device, description.component)
        await self._async_write(component.write(description.field, value))
