"""Vet values before they are written to the device."""

from __future__ import annotations

from collections.abc import Callable

from .const import MAX_CHARGING_CURRENT, MIN_CHARGING_CURRENT


def in_range(low: float, high: float) -> Callable[[float], float]:
    """Accept a value within ``low`` and ``high``, inclusive."""

    def validate(value: float) -> float:
        if not low <= value <= high:
            raise ValueError(f"{value} is outside {low}..{high}")
        return value

    return validate


def charging_current(value: float) -> float:
    """Accept a current a vehicle may be told to draw."""
    return in_range(MIN_CHARGING_CURRENT, MAX_CHARGING_CURRENT)(value)


def charging_current_or_off(value: float) -> float:
    """Accept a charging current, or 0 to stop charging."""
    if value == 0:
        return value
    return charging_current(value)
