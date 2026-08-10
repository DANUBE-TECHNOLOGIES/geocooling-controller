"""Conservative floor-surface temperature estimation helpers.

The installed site has no dedicated floor-surface probe. For condensation
protection we derive a conservative reference from the two measured floor-loop
temperatures. This module is pure: it does not read databases or touch hardware.
"""

from __future__ import annotations

import math
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SurfaceEstimate:
    available: bool
    temperature_c: float | None
    floor_supply_temperature_c: float | None
    floor_return_temperature_c: float | None
    mean_water_temperature_c: float | None
    bias_c: float
    method: str
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return {
            "available": self.available,
            "temperature_c": self.temperature_c,
            "floor_supply_temperature_c": self.floor_supply_temperature_c,
            "floor_return_temperature_c": self.floor_return_temperature_c,
            "mean_water_temperature_c": self.mean_water_temperature_c,
            "bias_c": self.bias_c,
            "method": self.method,
            "reason": self.reason,
        }


def _finite(value: Any) -> float | None:
    if value is None:
        return None
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


def configured_surface_estimation_bias_c() -> float:
    """Return the configured conservative bias applied to mean water temp.

    A non-positive value is enforced: configuration can make the estimate more
    conservative, never warmer/less restrictive than the raw mean-water value.
    """

    try:
        requested = float(os.getenv("GEOCOOLING_SURFACE_ESTIMATION_BIAS_C", "-0.5"))
    except ValueError:
        requested = -0.5
    if not math.isfinite(requested):
        requested = -0.5
    return min(0.0, requested)


def estimate_floor_surface_temperature(
    floor_supply_temperature_c: Any,
    floor_return_temperature_c: Any,
    *,
    bias_c: float | None = None,
) -> SurfaceEstimate:
    """Estimate a conservative floor-surface reference from supply + return.

    The arithmetic mean of supply and return water temperatures is used as the
    hydronic reference, then a non-positive safety bias is applied. In cooling,
    floor surface temperature is normally warmer than the water-loop reference;
    using the colder derived reference therefore makes the dew-point gate more
    restrictive. The estimate must still be validated during field commissioning.
    """

    supply = _finite(floor_supply_temperature_c)
    return_ = _finite(floor_return_temperature_c)
    selected_bias = configured_surface_estimation_bias_c() if bias_c is None else float(bias_c)
    if not math.isfinite(selected_bias):
        selected_bias = -0.5
    selected_bias = min(0.0, selected_bias)

    if supply is None or return_ is None:
        return SurfaceEstimate(
            available=False,
            temperature_c=None,
            floor_supply_temperature_c=supply,
            floor_return_temperature_c=return_,
            mean_water_temperature_c=None,
            bias_c=selected_bias,
            method="floor_supply_return_mean_conservative",
            reason="Both floor supply and return temperatures are required.",
        )

    mean_water = (supply + return_) / 2.0
    estimate = mean_water + selected_bias

    return SurfaceEstimate(
        available=True,
        temperature_c=round(estimate, 3),
        floor_supply_temperature_c=round(supply, 3),
        floor_return_temperature_c=round(return_, 3),
        mean_water_temperature_c=round(mean_water, 3),
        bias_c=round(selected_bias, 3),
        method="floor_supply_return_mean_conservative",
        reason=(
            "Conservative surface reference derived from floor supply/return "
            "mean with a non-positive safety bias."
        ),
    )
