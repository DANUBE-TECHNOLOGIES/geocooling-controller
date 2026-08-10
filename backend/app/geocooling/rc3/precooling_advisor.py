"""Shadow-only pre-cooling advisor built on RC3.5 weather/inertia trajectories.

The advisor never authorizes or calls the controller. It converts passive
thermal forecasts into an explainable recommendation window that can be
observed and calibrated before field commissioning is complete.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from math import isfinite
from typing import Any, Mapping, Sequence
import os


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if isfinite(result) else None


def _env_float(name: str, default: float, minimum: float, maximum: float) -> float:
    raw = os.getenv(name)
    if raw is None or not raw.strip():
        return default
    try:
        value = float(raw)
    except ValueError:
        return default
    return max(minimum, min(maximum, value))


def _trajectories(prediction: Mapping[str, Any]) -> dict[str, list[Mapping[str, Any]]]:
    result: dict[str, list[Mapping[str, Any]]] = {}
    raw = prediction.get("trajectories")
    if not isinstance(raw, Sequence) or isinstance(raw, (str, bytes, bytearray)):
        return result
    for item in raw:
        if not isinstance(item, Mapping):
            continue
        scenario = str(item.get("scenario") or "")
        points = item.get("points")
        if scenario and isinstance(points, Sequence):
            result[scenario] = [point for point in points if isinstance(point, Mapping)]
    return result


def _point_map(points: Sequence[Mapping[str, Any]]) -> dict[int, Mapping[str, Any]]:
    mapped: dict[int, Mapping[str, Any]] = {}
    for point in points:
        try:
            horizon = int(point.get("horizon_minutes"))
        except (TypeError, ValueError):
            continue
        mapped[horizon] = point
    return mapped


class PreCoolingAdvisor:
    """Explainable, passive recommendation engine for pre-cooling timing."""

    SCHEMA = "geocooling.rc35.precooling-advisory.v1"

    def __init__(
        self,
        *,
        comfort_target_c: float | None = None,
        comfort_max_c: float | None = None,
        minimum_confidence: float | None = None,
        minimum_lead_minutes: int = 30,
        maximum_lead_minutes: int = 360,
    ) -> None:
        self.comfort_target_c = (
            comfort_target_c
            if comfort_target_c is not None
            else _env_float("COMFORT_TARGET_TEMPERATURE", 24.0, 18.0, 30.0)
        )
        self.comfort_max_c = (
            comfort_max_c
            if comfort_max_c is not None
            else _env_float("COMFORT_MAX_TEMPERATURE", 25.0, self.comfort_target_c, 32.0)
        )
        self.minimum_confidence = (
            minimum_confidence
            if minimum_confidence is not None
            else _env_float("GEOCOOLING_PRECOOL_MIN_CONFIDENCE", 0.45, 0.0, 1.0)
        )
        self.minimum_lead_minutes = max(0, int(minimum_lead_minutes))
        self.maximum_lead_minutes = max(self.minimum_lead_minutes, int(maximum_lead_minutes))

    def advise(self, prediction: Mapping[str, Any]) -> dict[str, Any]:
        weather_input = prediction.get("weather_input")
        weather_input = weather_input if isinstance(weather_input, Mapping) else {}
        generated_raw = prediction.get("generated_at")
        try:
            generated_at = datetime.fromisoformat(str(generated_raw).replace("Z", "+00:00"))
        except (TypeError, ValueError):
            generated_at = datetime.now(timezone.utc)
        if generated_at.tzinfo is None:
            generated_at = generated_at.replace(tzinfo=timezone.utc)

        trajectories = _trajectories(prediction)
        baseline = _point_map(trajectories.get("BASELINE", []))
        soft = _point_map(trajectories.get("SOFT_COOLING", []))
        full = _point_map(trajectories.get("FULL_COOLING", []))

        if not baseline:
            raise ValueError("BASELINE trajectory is required")

        weather_degraded = bool(weather_input.get("degraded", True))
        crossing_horizon: int | None = None
        crossing_point: Mapping[str, Any] | None = None

        for horizon in sorted(baseline):
            temperature = _number(baseline[horizon].get("predicted_indoor_temperature_c"))
            if temperature is not None and temperature >= self.comfort_max_c:
                crossing_horizon = horizon
                crossing_point = baseline[horizon]
                break

        peak_horizon = max(
            baseline,
            key=lambda horizon: _number(baseline[horizon].get("predicted_indoor_temperature_c")) or -999.0,
        )
        peak_temperature = _number(baseline[peak_horizon].get("predicted_indoor_temperature_c"))

        if crossing_horizon is None or crossing_point is None:
            return self._result(
                generated_at=generated_at,
                state="NO_PRECOOL_NEEDED",
                reason="Baseline trajectory does not cross the configured comfort maximum.",
                weather_degraded=weather_degraded,
                crossing_horizon=None,
                crossing_temperature=None,
                confidence=None,
                recommended_scenario=None,
                recommended_start_horizon=None,
                lead_minutes=0,
                peak_temperature=peak_temperature,
                peak_horizon=peak_horizon,
            )

        confidence = _number(crossing_point.get("confidence")) or 0.0
        baseline_temp = _number(crossing_point.get("predicted_indoor_temperature_c"))
        soft_temp = _number(soft.get(crossing_horizon, {}).get("predicted_indoor_temperature_c"))
        full_temp = _number(full.get(crossing_horizon, {}).get("predicted_indoor_temperature_c"))

        recommended_scenario = "FULL_COOLING"
        cooled_temp = full_temp
        if soft_temp is not None and soft_temp <= self.comfort_target_c:
            recommended_scenario = "SOFT_COOLING"
            cooled_temp = soft_temp
        elif full_temp is not None and full_temp <= self.comfort_max_c:
            recommended_scenario = "FULL_COOLING"
            cooled_temp = full_temp
        elif soft_temp is not None and full_temp is None:
            recommended_scenario = "SOFT_COOLING"
            cooled_temp = soft_temp

        avoided_c = max(0.0, (baseline_temp or 0.0) - (cooled_temp or baseline_temp or 0.0))
        excess_c = max(0.0, (baseline_temp or self.comfort_max_c) - self.comfort_target_c)

        # Infer a conservative lead from the predicted cooling advantage at the
        # crossing horizon. Sparse RC3 horizons deliberately limit precision.
        if avoided_c > 0 and crossing_horizon > 0:
            effective_rate_c_per_hour = avoided_c / max(0.5, crossing_horizon / 60.0)
            estimated_hours = excess_c / max(0.05, effective_rate_c_per_hour)
            lead_minutes = int(round(estimated_hours * 60 / 30.0) * 30)
        else:
            lead_minutes = self.maximum_lead_minutes

        lead_minutes = max(self.minimum_lead_minutes, min(self.maximum_lead_minutes, lead_minutes))
        recommended_start_horizon = max(0, crossing_horizon - lead_minutes)

        if weather_degraded:
            state = "WEATHER_DEGRADED"
            reason = "Forecast is degraded; pre-cooling timing is advisory only and not reliable enough for automation."
        elif confidence < self.minimum_confidence:
            state = "LOW_CONFIDENCE"
            reason = "Thermal forecast confidence is below the pre-cooling automation threshold."
        elif recommended_start_horizon == 0:
            state = "PRECOOL_NOW_ADVISORY"
            reason = "Comfort limit is forecast soon enough that the conservative pre-cooling window starts now."
        else:
            state = "PRECOOL_WINDOW_IDENTIFIED"
            reason = "A passive pre-cooling window was identified before the first comfort-limit crossing."

        return self._result(
            generated_at=generated_at,
            state=state,
            reason=reason,
            weather_degraded=weather_degraded,
            crossing_horizon=crossing_horizon,
            crossing_temperature=baseline_temp,
            confidence=confidence,
            recommended_scenario=recommended_scenario,
            recommended_start_horizon=recommended_start_horizon,
            lead_minutes=lead_minutes,
            peak_temperature=peak_temperature,
            peak_horizon=peak_horizon,
            avoided_c=avoided_c,
            cooled_temperature=cooled_temp,
        )

    def _result(
        self,
        *,
        generated_at: datetime,
        state: str,
        reason: str,
        weather_degraded: bool,
        crossing_horizon: int | None,
        crossing_temperature: float | None,
        confidence: float | None,
        recommended_scenario: str | None,
        recommended_start_horizon: int | None,
        lead_minutes: int,
        peak_temperature: float | None,
        peak_horizon: int,
        avoided_c: float | None = None,
        cooled_temperature: float | None = None,
    ) -> dict[str, Any]:
        crossing_at = (
            generated_at + timedelta(minutes=crossing_horizon)
            if crossing_horizon is not None
            else None
        )
        start_at = (
            generated_at + timedelta(minutes=recommended_start_horizon)
            if recommended_start_horizon is not None
            else None
        )
        return {
            "schema": self.SCHEMA,
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SHADOW",
            "state": state,
            "reason": reason,
            "comfort": {
                "target_temperature_c": round(self.comfort_target_c, 3),
                "maximum_temperature_c": round(self.comfort_max_c, 3),
            },
            "forecast": {
                "weather_degraded": weather_degraded,
                "first_limit_crossing_horizon_minutes": crossing_horizon,
                "first_limit_crossing_at": crossing_at.isoformat() if crossing_at else None,
                "first_limit_crossing_temperature_c": crossing_temperature,
                "confidence_at_crossing": confidence,
                "minimum_confidence": self.minimum_confidence,
                "baseline_peak_temperature_c": peak_temperature,
                "baseline_peak_horizon_minutes": peak_horizon,
            },
            "recommendation": {
                "scenario": recommended_scenario,
                "lead_minutes": lead_minutes,
                "start_horizon_minutes": recommended_start_horizon,
                "start_at": start_at.isoformat() if start_at else None,
                "predicted_temperature_with_cooling_c": cooled_temperature,
                "predicted_avoided_temperature_c": avoided_c,
            },
            "safety": {
                "advisory_only": True,
                "controller_authorized": False,
                "controller_called": False,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
                "promotion_to_controller_allowed": False,
            },
        }
