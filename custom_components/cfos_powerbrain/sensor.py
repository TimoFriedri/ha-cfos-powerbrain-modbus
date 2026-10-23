"""Sensors of the cFos Power Brain."""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import date, datetime
from decimal import Decimal
from typing import Any, Self

from homeassistant.components.sensor import (
    RestoreSensor,
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    EntityCategory,
    UnitOfElectricCurrent,
    UnitOfEnergy,
    UnitOfPower,
    UnitOfTemperature,
    UnitOfTime,
)
from homeassistant.core import HomeAssistant, callback
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback
from homeassistant.helpers.restore_state import ExtraStoredData, RestoreEntity
from homeassistant.helpers.typing import StateType
from homeassistant.util import slugify

from .cfos_modbus import (
    METERS,
    CfosChargingManager,
    CfosDevice,
    CfosS0Meter,
    CfosWallbox,
    ChargePilotState,
)
from .coordinator import CfosConfigEntry, CfosUnitData
from .entity import CfosEntity, CfosEntityDescription

PARALLEL_UPDATES = 0


@dataclass(frozen=True, kw_only=True)
class CfosSensorEntityDescription[DeviceT: CfosDevice](
    SensorEntityDescription, CfosEntityDescription
):
    """Describe a sensor reading one value of a cFos unit."""

    value_fn: Callable[[DeviceT], StateType]


def _component_value(component: str, field: str) -> Callable[[CfosDevice], StateType]:
    """Read one field off a component, or None while the component is absent."""

    def value(device: CfosDevice) -> StateType:
        found = getattr(device, component)
        result: StateType = getattr(found, field, None) if found else None
        return result

    return value


def _phase_currents[DeviceT: CfosDevice](
    device_type: type[DeviceT],
    component: str,
    *,
    key: str = "current",
    translation_key: str = "phase_current",
    enabled: bool = True,
) -> tuple[CfosSensorEntityDescription[DeviceT], ...]:
    """Describe the three phase currents of a meter component."""
    return tuple(
        CfosSensorEntityDescription[DeviceT](
            key=f"{key}_l{phase}",
            translation_key=translation_key,
            translation_placeholders={"phase": f"L{phase}"},
            component=component,
            device_class=SensorDeviceClass.CURRENT,
            native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=1,
            entity_registry_enabled_default=enabled,
            value_fn=_component_value(component, f"current_l{phase}"),
        )
        for phase in (1, 2, 3)
    )


WALLBOX_SENSORS: tuple[CfosSensorEntityDescription[CfosWallbox], ...] = (
    CfosSensorEntityDescription[CfosWallbox](
        key="charge_pilot_state",
        translation_key="charge_pilot_state",
        component="status",
        device_class=SensorDeviceClass.ENUM,
        options=[state.name.lower() for state in ChargePilotState],
        value_fn=lambda device: (
            None
            if (state := device.status.charge_pilot_state) is None
            else state.name.lower()
        ),
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="charging_current",
        translation_key="charging_current",
        component="status",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        state_class=SensorStateClass.MEASUREMENT,
        suggested_display_precision=1,
        value_fn=lambda device: device.status.charging_current,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="cable_current",
        translation_key="cable_current",
        component="status",
        device_class=SensorDeviceClass.CURRENT,
        native_unit_of_measurement=UnitOfElectricCurrent.AMPERE,
        entity_category=EntityCategory.DIAGNOSTIC,
        suggested_display_precision=1,
        value_fn=lambda device: device.status.cable_current,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="last_rfid",
        translation_key="last_rfid",
        component="status",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.status.last_rfid or None,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="power",
        component="meter",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.meter.power if device.meter else None,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="energy",
        translation_key="total_energy",
        component="meter",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.meter.energy if device.meter else None,
    ),
    *_phase_currents(CfosWallbox, "meter"),
    CfosSensorEntityDescription[CfosWallbox](
        key="active_phases",
        translation_key="active_phases",
        component="meter",
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.meter.active_phases if device.meter else None,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="temperature",
        translation_key="controller_temperature",
        component="health",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        value_fn=lambda device: device.health.temperature if device.health else None,
    ),
    CfosSensorEntityDescription[CfosWallbox](
        key="restart_count",
        translation_key="restart_count",
        component="health",
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.health.restart_count if device.health else None,
    ),
)

S0_METER_SENSORS: tuple[CfosSensorEntityDescription[CfosS0Meter], ...] = (
    CfosSensorEntityDescription[CfosS0Meter](
        key="power",
        component="readings",
        device_class=SensorDeviceClass.POWER,
        native_unit_of_measurement=UnitOfPower.WATT,
        state_class=SensorStateClass.MEASUREMENT,
        value_fn=lambda device: device.readings.power,
    ),
    CfosSensorEntityDescription[CfosS0Meter](
        key="energy",
        translation_key="total_energy",
        component="readings",
        device_class=SensorDeviceClass.ENERGY,
        native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
        suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
        state_class=SensorStateClass.TOTAL_INCREASING,
        value_fn=lambda device: device.readings.energy,
    ),
    *_phase_currents(CfosS0Meter, "readings"),
    CfosSensorEntityDescription[CfosS0Meter](
        key="pulses",
        translation_key="pulses",
        component="readings",
        state_class=SensorStateClass.TOTAL_INCREASING,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.readings.pulses,
    ),
    CfosSensorEntityDescription[CfosS0Meter](
        key="time_per_pulse",
        translation_key="time_per_pulse",
        component="readings",
        device_class=SensorDeviceClass.DURATION,
        native_unit_of_measurement=UnitOfTime.MILLISECONDS,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
        value_fn=lambda device: device.readings.time_per_pulse,
    ),
)

CHARGING_MANAGER_SENSORS: tuple[
    CfosSensorEntityDescription[CfosChargingManager], ...
] = (
    *(
        CfosSensorEntityDescription[CfosChargingManager](
            key=f"{meter}_power",
            translation_key=f"{meter}_power",
            component=meter,
            device_class=SensorDeviceClass.POWER,
            native_unit_of_measurement=UnitOfPower.WATT,
            state_class=SensorStateClass.MEASUREMENT,
            suggested_display_precision=0,
            value_fn=_component_value(meter, "power"),
        )
        for meter in METERS
    ),
    *_phase_currents(
        CfosChargingManager,
        "grid",
        key="grid_current",
        translation_key="grid_current",
        enabled=False,
    ),
    *_phase_currents(
        CfosChargingManager,
        "wallbox_available",
        key="wallbox_available_current",
        translation_key="wallbox_available_current",
        enabled=False,
    ),
    *(
        CfosSensorEntityDescription[CfosChargingManager](
            key=f"grid_energy_{direction}",
            translation_key=f"grid_energy_{direction}",
            component="grid",
            device_class=SensorDeviceClass.ENERGY,
            native_unit_of_measurement=UnitOfEnergy.WATT_HOUR,
            suggested_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
            state_class=SensorStateClass.TOTAL_INCREASING,
            entity_registry_enabled_default=False,
            value_fn=_component_value("grid", f"energy_{direction}"),
        )
        for direction in ("imported", "exported")
    ),
)

SESSION_ENERGY = CfosSensorEntityDescription[CfosWallbox](
    key="session_energy",
    translation_key="session_energy",
    component="meter",
    device_class=SensorDeviceClass.ENERGY,
    native_unit_of_measurement=UnitOfEnergy.KILO_WATT_HOUR,
    state_class=SensorStateClass.TOTAL_INCREASING,
    suggested_display_precision=2,
    value_fn=lambda device: None,  # derived, see CfosSessionEnergySensor
)


async def async_setup_entry(
    hass: HomeAssistant,
    entry: CfosConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensors."""
    runtime_data = entry.runtime_data
    wallbox = runtime_data.wallbox
    entities: list[SensorEntity] = [
        _create(wallbox, description)
        for description in WALLBOX_SENSORS
        if description.supported(wallbox.device)
    ]
    if SESSION_ENERGY.supported(wallbox.device):
        entities.append(CfosSessionEnergySensor(wallbox, SESSION_ENERGY))
    for meter in runtime_data.s0_meters.values():
        entities.extend(
            _create(meter, description)
            for description in S0_METER_SENSORS
            if description.supported(meter.device)
        )
    if (manager := runtime_data.charging_manager) is not None:
        entities.extend(
            _create(manager, description)
            for description in CHARGING_MANAGER_SENSORS
            if description.supported(manager.device)
        )
        entities.extend(
            CfosVariableSensor(manager, index, name)
            for index, name in enumerate(manager.device.variable_names)
            if name
        )
    async_add_entities(entities)


def _create[DeviceT: CfosDevice](
    unit: CfosUnitData[DeviceT], description: CfosSensorEntityDescription[DeviceT]
) -> CfosSensor[DeviceT]:
    """A plain sensor, or one that keeps its total across outages."""
    if description.state_class is SensorStateClass.TOTAL_INCREASING:
        return CfosTotalSensor(unit, description)
    return CfosSensor(unit, description)


class CfosSensor[DeviceT: CfosDevice](CfosEntity[DeviceT], SensorEntity):
    """A sensor reading one value of a cFos unit."""

    entity_description: CfosSensorEntityDescription[DeviceT]

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """The value from the most recent poll."""
        return self.entity_description.value_fn(self.device)


class CfosTotalSensor[DeviceT: CfosDevice](CfosSensor[DeviceT], RestoreSensor):
    """A counter: it holds its last value while the device is unreachable.

    A gap in a total damages long-term statistics and the energy dashboard,
    so the counter stays available and restores its value across restarts.
    """

    @property
    def available(self) -> bool:
        """Always; the last total stays valid while the device is away."""
        return True

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """The last total seen."""
        return self._attr_native_value

    async def async_added_to_hass(self) -> None:
        """Restore the last total, then take the current one."""
        await super().async_added_to_hass()
        if (last := await self.async_get_last_sensor_data()) is not None:
            self._attr_native_value = last.native_value
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Take the new total."""
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        """Keep the new value unless it is a glitch just below the last one."""
        value = self.entity_description.value_fn(self.device)
        if not isinstance(value, int | float):
            return
        last = self._attr_native_value
        if isinstance(last, int | float) and last * 0.99 <= value < last:
            return
        self._attr_native_value = value


@dataclass
class SessionExtraStoredData(ExtraStoredData):
    """What the session energy sensor needs across a restart."""

    native_value: float | None
    start_energy: int | None
    vehicle_connected: bool

    def as_dict(self) -> dict[str, Any]:
        """The data as a dict, for the restore state store."""
        return asdict(self)

    @classmethod
    def from_dict(cls, restored: dict[str, Any]) -> Self | None:
        """Rebuild the data, or None if the stored shape is unknown."""
        try:
            return cls(
                restored["native_value"],
                restored["start_energy"],
                restored["vehicle_connected"],
            )
        except KeyError:
            return None


class CfosSessionEnergySensor(CfosSensor[CfosWallbox], RestoreEntity):
    """Energy charged since the vehicle was plugged in.

    Derived from the meter total: the session starts when the control pilot
    sees a vehicle and the value stays after unplugging, until the next one.
    """

    _start_energy: int | None = None
    _vehicle_connected = False

    @property
    def available(self) -> bool:
        """Always; the last session stays valid while the device is away."""
        return True

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """Energy of the current or most recent session, in kWh."""
        return self._attr_native_value

    @property
    def extra_restore_state_data(self) -> SessionExtraStoredData:
        """Remember where the session started."""
        value = self._attr_native_value
        return SessionExtraStoredData(
            float(value) if isinstance(value, int | float) else None,
            self._start_energy,
            self._vehicle_connected,
        )

    async def async_added_to_hass(self) -> None:
        """Pick up the session where it was before the restart."""
        await super().async_added_to_hass()
        if (extra := await self.async_get_last_extra_data()) is not None and (
            data := SessionExtraStoredData.from_dict(extra.as_dict())
        ) is not None:
            self._attr_native_value = data.native_value
            self._start_energy = data.start_energy
            self._vehicle_connected = data.vehicle_connected
        self._process_data()

    @callback
    def _handle_coordinator_update(self) -> None:
        """Follow the session."""
        self._process_data()
        super()._handle_coordinator_update()

    def _process_data(self) -> None:
        """Start a session on plug-in, and count energy while it lasts."""
        meter = self.device.meter
        connected = self.device.status.vehicle_connected
        if meter is None or meter.energy is None or connected is None:
            return
        energy = meter.energy
        if connected:
            if (
                not self._vehicle_connected
                or self._start_energy is None
                or energy < self._start_energy
            ):
                self._start_energy = energy
            self._attr_native_value = round((energy - self._start_energy) / 1000, 3)
        self._vehicle_connected = connected


class CfosVariableSensor(CfosSensor[CfosChargingManager]):
    """The value of a Charging Manager variable.

    Read-only on purpose: writing a value replaces the variable's formula, so
    that is the separate set_charging_manager_variable action.
    """

    def __init__(
        self, unit: CfosUnitData[CfosChargingManager], index: int, name: str
    ) -> None:
        """Initialize the sensor for the variable at ``index``."""
        super().__init__(
            unit,
            CfosSensorEntityDescription[CfosChargingManager](
                key=f"variable_{slugify(name)}",
                translation_key="variable",
                translation_placeholders={"name": name},
                component="variables",
                value_fn=lambda device: None,
            ),
        )
        self._index = index

    @property
    def native_value(self) -> StateType | date | datetime | Decimal:
        """The variable's value from the most recent poll."""
        variables = self.device.variables
        if variables is None or self._index >= len(variables.variables):
            return None
        return variables.variables[self._index].value
