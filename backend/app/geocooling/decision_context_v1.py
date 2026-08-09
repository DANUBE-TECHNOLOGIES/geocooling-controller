"""
GeoCooling RC1.7A — canonical decision context.

This module is additive and side-effect free. It does not command hardware,
publish MQTT messages, start services, or write to the database.
"""

from __future__ import annotations

import math
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class DecisionAction(str, Enum):
    WAIT = "WAIT"
    PRECOOL = "PRECOOL"
    START_COOLING = "START_COOLING"
    HOLD_COOLING = "HOLD_COOLING"
    STOP_COOLING = "STOP_COOLING"
    BLOCKED = "BLOCKED"


class RiskLevel(str, Enum):
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


class DataQuality(str, Enum):
    GOOD = "GOOD"
    DEGRADED = "DEGRADED"
    INSUFFICIENT = "INSUFFICIENT"
    UNKNOWN = "UNKNOWN"


@dataclass(frozen=True, slots=True)
class DecisionRisk:
    code: str
    level: RiskLevel
    message: str
    blocking: bool = False
    value: float | None = None
    threshold: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            **asdict(self),
            "level": self.level.value,
        }


@dataclass(frozen=True, slots=True)
class DecisionForecast:
    horizon_minutes: int
    indoor_temperature_c: float | None
    confidence: float | None
    source: str = "unknown"

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class DecisionContext:
    timestamp: str

    indoor_temperature_c: float | None = None
    indoor_humidity_pct: float | None = None
    outdoor_temperature_c: float | None = None
    dew_point_c: float | None = None
    floor_surface_temperature_c: float | None = None
    floor_supply_temperature_c: float | None = None
    floor_return_temperature_c: float | None = None
    source_in_temperature_c: float | None = None
    source_out_temperature_c: float | None = None
    flow_l_min: float | None = None

    comfort_target_c: float | None = None
    cooling_start_threshold_c: float | None = None
    cooling_stop_threshold_c: float | None = None
    condensation_margin_c: float | None = None
    minimum_condensation_margin_c: float | None = None

    weather_available: bool = False
    historian_available: bool = False
    learning_available: bool = False
    prediction_available: bool = False
    hardware_available: bool = False

    building_inertia: str | None = None
    sensor_quality: DataQuality = DataQuality.UNKNOWN
    weather_quality: DataQuality = DataQuality.UNKNOWN
    learning_quality: DataQuality = DataQuality.UNKNOWN
    prediction_quality: DataQuality = DataQuality.UNKNOWN

    forecasts: tuple[DecisionForecast, ...] = field(default_factory=tuple)
    risks: tuple[DecisionRisk, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)

    recommended_action: DecisionAction = DecisionAction.WAIT
    confidence: float = 0.0
    recommended_start_at: str | None = None
    recommended_stop_at: str | None = None
    estimated_thermal_gain_kwh: float | None = None
    estimated_electrical_energy_kwh: float | None = None

    metadata: Mapping[str, Any] = field(default_factory=dict)

    @property
    def blocking(self) -> bool:
        return any(risk.blocking for risk in self.risks)

    @property
    def highest_risk_level(self) -> RiskLevel:
        order = {
            RiskLevel.LOW: 0,
            RiskLevel.MEDIUM: 1,
            RiskLevel.HIGH: 2,
            RiskLevel.CRITICAL: 3,
        }

        if not self.risks:
            return RiskLevel.LOW

        return max(
            (risk.level for risk in self.risks),
            key=order.__getitem__,
        )

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "geocooling.decision-context.v1",
            "timestamp": self.timestamp,
            "measurements": {
                "indoor_temperature_c": self.indoor_temperature_c,
                "indoor_humidity_pct": self.indoor_humidity_pct,
                "outdoor_temperature_c": self.outdoor_temperature_c,
                "dew_point_c": self.dew_point_c,
                "floor_surface_temperature_c": self.floor_surface_temperature_c,
                "floor_supply_temperature_c": self.floor_supply_temperature_c,
                "floor_return_temperature_c": self.floor_return_temperature_c,
                "source_in_temperature_c": self.source_in_temperature_c,
                "source_out_temperature_c": self.source_out_temperature_c,
                "flow_l_min": self.flow_l_min,
            },
            "configuration": {
                "comfort_target_c": self.comfort_target_c,
                "cooling_start_threshold_c": self.cooling_start_threshold_c,
                "cooling_stop_threshold_c": self.cooling_stop_threshold_c,
                "condensation_margin_c": self.condensation_margin_c,
                "minimum_condensation_margin_c": (
                    self.minimum_condensation_margin_c
                ),
            },
            "availability": {
                "weather": self.weather_available,
                "historian": self.historian_available,
                "learning": self.learning_available,
                "prediction": self.prediction_available,
                "hardware": self.hardware_available,
            },
            "quality": {
                "sensors": self.sensor_quality.value,
                "weather": self.weather_quality.value,
                "learning": self.learning_quality.value,
                "prediction": self.prediction_quality.value,
            },
            "building_inertia": self.building_inertia,
            "forecasts": [forecast.as_dict() for forecast in self.forecasts],
            "risks": [risk.as_dict() for risk in self.risks],
            "reasons": list(self.reasons),
            "recommendation": {
                "action": self.recommended_action.value,
                "confidence": self.confidence,
                "recommended_start_at": self.recommended_start_at,
                "recommended_stop_at": self.recommended_stop_at,
                "estimated_thermal_gain_kwh": self.estimated_thermal_gain_kwh,
                "estimated_electrical_energy_kwh": (
                    self.estimated_electrical_energy_kwh
                ),
            },
            "blocking": self.blocking,
            "highest_risk_level": self.highest_risk_level.value,
            "metadata": dict(self.metadata),
        }


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_number(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def clamp_confidence(value: Any) -> float:
    converted = finite_number(value)

    if converted is None:
        return 0.0

    return max(0.0, min(1.0, converted))


def normalize_quality(value: Any) -> DataQuality:
    if isinstance(value, DataQuality):
        return value

    normalized = str(value or "").strip().upper()

    try:
        return DataQuality(normalized)
    except ValueError:
        return DataQuality.UNKNOWN


def normalize_action(value: Any) -> DecisionAction:
    if isinstance(value, DecisionAction):
        return value

    normalized = str(value or "").strip().upper()

    try:
        return DecisionAction(normalized)
    except ValueError:
        return DecisionAction.WAIT


def build_decision_context(
    *,
    timestamp: str | None = None,
    measurements: Mapping[str, Any] | None = None,
    configuration: Mapping[str, Any] | None = None,
    availability: Mapping[str, Any] | None = None,
    quality: Mapping[str, Any] | None = None,
    forecasts: Sequence[DecisionForecast] | None = None,
    risks: Sequence[DecisionRisk] | None = None,
    reasons: Sequence[str] | None = None,
    recommendation: Mapping[str, Any] | None = None,
    metadata: Mapping[str, Any] | None = None,
) -> DecisionContext:
    measurements = measurements or {}
    configuration = configuration or {}
    availability = availability or {}
    quality = quality or {}
    recommendation = recommendation or {}

    return DecisionContext(
        timestamp=timestamp or utc_now_iso(),
        indoor_temperature_c=finite_number(
            measurements.get("indoor_temperature_c")
        ),
        indoor_humidity_pct=finite_number(
            measurements.get("indoor_humidity_pct")
        ),
        outdoor_temperature_c=finite_number(
            measurements.get("outdoor_temperature_c")
        ),
        dew_point_c=finite_number(measurements.get("dew_point_c")),
        floor_surface_temperature_c=finite_number(
            measurements.get("floor_surface_temperature_c")
        ),
        floor_supply_temperature_c=finite_number(
            measurements.get("floor_supply_temperature_c")
        ),
        floor_return_temperature_c=finite_number(
            measurements.get("floor_return_temperature_c")
        ),
        source_in_temperature_c=finite_number(
            measurements.get("source_in_temperature_c")
        ),
        source_out_temperature_c=finite_number(
            measurements.get("source_out_temperature_c")
        ),
        flow_l_min=finite_number(measurements.get("flow_l_min")),
        comfort_target_c=finite_number(configuration.get("comfort_target_c")),
        cooling_start_threshold_c=finite_number(
            configuration.get("cooling_start_threshold_c")
        ),
        cooling_stop_threshold_c=finite_number(
            configuration.get("cooling_stop_threshold_c")
        ),
        condensation_margin_c=finite_number(
            configuration.get("condensation_margin_c")
        ),
        minimum_condensation_margin_c=finite_number(
            configuration.get("minimum_condensation_margin_c")
        ),
        weather_available=bool(availability.get("weather", False)),
        historian_available=bool(availability.get("historian", False)),
        learning_available=bool(availability.get("learning", False)),
        prediction_available=bool(availability.get("prediction", False)),
        hardware_available=bool(availability.get("hardware", False)),
        building_inertia=(
            str(configuration["building_inertia"])
            if configuration.get("building_inertia") is not None
            else None
        ),
        sensor_quality=normalize_quality(quality.get("sensors")),
        weather_quality=normalize_quality(quality.get("weather")),
        learning_quality=normalize_quality(quality.get("learning")),
        prediction_quality=normalize_quality(quality.get("prediction")),
        forecasts=tuple(forecasts or ()),
        risks=tuple(risks or ()),
        reasons=tuple(str(reason) for reason in (reasons or ())),
        recommended_action=normalize_action(recommendation.get("action")),
        confidence=clamp_confidence(recommendation.get("confidence")),
        recommended_start_at=recommendation.get("recommended_start_at"),
        recommended_stop_at=recommendation.get("recommended_stop_at"),
        estimated_thermal_gain_kwh=finite_number(
            recommendation.get("estimated_thermal_gain_kwh")
        ),
        estimated_electrical_energy_kwh=finite_number(
            recommendation.get("estimated_electrical_energy_kwh")
        ),
        metadata=dict(metadata or {}),
    )
