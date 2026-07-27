from __future__ import annotations

from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.geocooling.safety import GeoCoolingSafetyManager


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class ThermalSample:
    captured_at: datetime
    indoor_temperature_c: float | None = None
    indoor_humidity_percent: float | None = None
    surface_temperature_c: float | None = None
    floor_supply_temperature_c: float | None = None
    floor_return_temperature_c: float | None = None
    source_inlet_temperature_c: float | None = None
    source_outlet_temperature_c: float | None = None
    outdoor_temperature_c: float | None = None


class ThermalEstimator:
    """Estimation thermique légère, déterministe et indépendante du matériel."""

    def __init__(self, *, history_size: int = 720) -> None:
        self._samples: deque[ThermalSample] = deque(maxlen=max(2, history_size))

    @staticmethod
    def _delta(first: float | None, second: float | None) -> float | None:
        if first is None or second is None:
            return None
        return round(first - second, 3)

    @staticmethod
    def _trend_per_hour(
        oldest_value: float | None,
        newest_value: float | None,
        elapsed_seconds: float,
    ) -> float | None:
        if oldest_value is None or newest_value is None or elapsed_seconds <= 0:
            return None
        return round((newest_value - oldest_value) * 3600.0 / elapsed_seconds, 3)

    def update(self, **values: float | None) -> dict[str, Any]:
        sample = ThermalSample(captured_at=utc_now(), **values)
        self._samples.append(sample)
        return self.status()

    def _trend_reference(self) -> ThermalSample | None:
        if len(self._samples) < 2:
            return None
        newest = self._samples[-1]
        target_age = 900.0
        candidates = list(self._samples)[:-1]
        return min(
            candidates,
            key=lambda item: abs((newest.captured_at - item.captured_at).total_seconds() - target_age),
        )

    def status(self) -> dict[str, Any]:
        if not self._samples:
            return {
                "available": False,
                "sample_count": 0,
                "reason": "Aucune mesure thermique reçue",
            }

        current = self._samples[-1]
        reference = self._trend_reference()
        elapsed = (
            (current.captured_at - reference.captured_at).total_seconds()
            if reference is not None
            else 0.0
        )

        dew_point = None
        if current.indoor_temperature_c is not None and current.indoor_humidity_percent is not None:
            dew_point = round(
                GeoCoolingSafetyManager.dew_point_c(
                    current.indoor_temperature_c,
                    current.indoor_humidity_percent,
                ),
                3,
            )

        floor_delta = self._delta(
            current.floor_return_temperature_c,
            current.floor_supply_temperature_c,
        )
        source_delta = self._delta(
            current.source_outlet_temperature_c,
            current.source_inlet_temperature_c,
        )
        dew_margin = self._delta(current.surface_temperature_c, dew_point)

        indoor_trend = self._trend_per_hour(
            reference.indoor_temperature_c if reference else None,
            current.indoor_temperature_c,
            elapsed,
        )
        surface_trend = self._trend_per_hour(
            reference.surface_temperature_c if reference else None,
            current.surface_temperature_c,
            elapsed,
        )

        cooling_active = floor_delta is not None and floor_delta > 0.15
        thermal_state = "unknown"
        if indoor_trend is not None:
            if indoor_trend <= -0.10:
                thermal_state = "cooling"
            elif indoor_trend >= 0.10:
                thermal_state = "warming"
            else:
                thermal_state = "stable"

        return {
            "available": True,
            "sample_count": len(self._samples),
            "captured_at": current.captured_at.isoformat(),
            "measurements": {
                key: value
                for key, value in asdict(current).items()
                if key != "captured_at"
            },
            "derived": {
                "dew_point_c": dew_point,
                "dew_point_margin_c": dew_margin,
                "floor_delta_t_c": floor_delta,
                "source_delta_t_c": source_delta,
                "indoor_temperature_trend_c_per_hour": indoor_trend,
                "surface_temperature_trend_c_per_hour": surface_trend,
                "cooling_exchange_detected": cooling_active,
                "thermal_state": thermal_state,
            },
            "trend_window_seconds": int(elapsed),
        }
