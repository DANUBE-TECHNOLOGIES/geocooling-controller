"""
GeoCooling RC3.0 — versioned decision contracts.

This module is side-effect free and defines the stable data exchanged by the
future predictive decision pipeline.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import Enum
from typing import Any, Mapping, Sequence


class DecisionMode(str, Enum):
    PASSIVE = "PASSIVE"
    SHADOW = "SHADOW"
    ACTIVE = "ACTIVE"


class DecisionAction(str, Enum):
    WAIT = "WAIT"
    PRECOOL = "PRECOOL"
    START_COOLING = "START_COOLING"
    HOLD_COOLING = "HOLD_COOLING"
    STOP_COOLING = "STOP_COOLING"
    BLOCKED = "BLOCKED"


class Severity(str, Enum):
    INFO = "INFO"
    LOW = "LOW"
    MEDIUM = "MEDIUM"
    HIGH = "HIGH"
    CRITICAL = "CRITICAL"


@dataclass(frozen=True, slots=True)
class MeasurementSet:
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


@dataclass(frozen=True, slots=True)
class ForecastPoint:
    horizon_minutes: int
    indoor_temperature_c: float | None
    confidence: float
    source: str


@dataclass(frozen=True, slots=True)
class ConstraintViolation:
    code: str
    severity: Severity
    message: str
    blocking: bool = False
    value: float | None = None
    threshold: float | None = None


@dataclass(frozen=True, slots=True)
class DecisionInput:
    schema: str
    generated_at: str
    mode: DecisionMode
    measurements: MeasurementSet
    forecasts: tuple[ForecastPoint, ...] = field(default_factory=tuple)
    constraints: tuple[ConstraintViolation, ...] = field(default_factory=tuple)
    configuration: Mapping[str, Any] = field(default_factory=dict)
    availability: Mapping[str, bool] = field(default_factory=dict)
    quality: Mapping[str, str] = field(default_factory=dict)
    metadata: Mapping[str, Any] = field(default_factory=dict)

    @classmethod
    def empty(
        cls,
        *,
        mode: DecisionMode = DecisionMode.PASSIVE,
    ) -> "DecisionInput":
        return cls(
            schema="geocooling.rc3.decision-input.v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
            mode=mode,
            measurements=MeasurementSet(),
        )


@dataclass(frozen=True, slots=True)
class ScenarioScore:
    name: str
    total_score: float
    comfort_score: float
    safety_score: float
    energy_score: float
    stability_score: float
    learning_score: float
    predicted_indoor_temperature_c: float | None
    estimated_runtime_minutes: int
    estimated_energy_kwh: float
    reasons: tuple[str, ...] = field(default_factory=tuple)


@dataclass(frozen=True, slots=True)
class DecisionOutput:
    schema: str
    generated_at: str
    mode: DecisionMode
    action: DecisionAction
    confidence: float
    selected_scenario: str | None
    scenarios: tuple[ScenarioScore, ...] = field(default_factory=tuple)
    reasons: tuple[str, ...] = field(default_factory=tuple)
    constraints: tuple[ConstraintViolation, ...] = field(default_factory=tuple)
    controller_authorized: bool = False
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["mode"] = self.mode.value
        payload["action"] = self.action.value

        for constraint in payload["constraints"]:
            constraint["severity"] = constraint["severity"].value

        return payload
