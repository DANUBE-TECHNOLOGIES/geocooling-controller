"""
GeoCooling RC2.1 — passive Scenario Engine.

Pure computation only:
- no hardware write;
- no MQTT publication;
- no database mutation;
- no background task;
- no outbound HTTP call.

The engine evaluates several cooling strategies from an already-built
DecisionContext payload.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from enum import Enum
from typing import Any, Mapping, Sequence


class ScenarioName(str, Enum):
    WAIT = "WAIT"
    PRECOOL_30 = "PRECOOL_30"
    PRECOOL_60 = "PRECOOL_60"
    COOL_NOW = "COOL_NOW"
    SOFT_COOLING = "SOFT_COOLING"


@dataclass(frozen=True, slots=True)
class ScenarioWeights:
    comfort: float = 0.40
    safety: float = 0.25
    energy: float = 0.20
    stability: float = 0.10
    learning: float = 0.05

    def normalized(self) -> "ScenarioWeights":
        total = (
            self.comfort
            + self.safety
            + self.energy
            + self.stability
            + self.learning
        )

        if total <= 0:
            return ScenarioWeights()

        return ScenarioWeights(
            comfort=self.comfort / total,
            safety=self.safety / total,
            energy=self.energy / total,
            stability=self.stability / total,
            learning=self.learning / total,
        )


@dataclass(frozen=True, slots=True)
class ScenarioResult:
    scenario: ScenarioName
    score: float
    comfort_score: float
    safety_score: float
    energy_score: float
    stability_score: float
    learning_score: float
    predicted_indoor_temperature_c: float | None
    estimated_runtime_minutes: int
    estimated_energy_kwh: float
    condensation_risk: str
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["scenario"] = self.scenario.value
        payload["reasons"] = list(self.reasons)
        return payload


@dataclass(frozen=True, slots=True)
class ScenarioDecision:
    selected: ScenarioResult
    alternatives: tuple[ScenarioResult, ...]
    explanation: tuple[str, ...]
    confidence: float
    passive: bool = True

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "geocooling.rc21.scenario-decision.v1",
            "selected": self.selected.as_dict(),
            "alternatives": [
                result.as_dict()
                for result in self.alternatives
            ],
            "explanation": list(self.explanation),
            "confidence": self.confidence,
            "passive": self.passive,
            "safety": {
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
                "outbound_http": False,
            },
        }


def _clamp(value: float, minimum: float = 0.0, maximum: float = 1.0) -> float:
    return max(minimum, min(maximum, value))


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if result != result:
        return None

    if result in {float("inf"), float("-inf")}:
        return None

    return result


def _nested(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, Mapping):
            return None

        current = current.get(key)

    return current


def _forecast_temperature(
    context: Mapping[str, Any],
    horizon_minutes: int,
) -> float | None:
    forecasts = context.get("forecasts")

    if not isinstance(forecasts, Sequence):
        return None

    candidates: list[tuple[int, float]] = []

    for item in forecasts:
        if not isinstance(item, Mapping):
            continue

        horizon = item.get("horizon_minutes")
        temperature = _number(
            item.get("indoor_temperature_c")
        )

        if isinstance(horizon, int) and temperature is not None:
            candidates.append((horizon, temperature))

    if not candidates:
        return None

    return min(
        candidates,
        key=lambda value: abs(value[0] - horizon_minutes),
    )[1]


class ScenarioEngine:
    def __init__(
        self,
        *,
        weights: ScenarioWeights | None = None,
        nominal_cooling_power_kw: float = 1.8,
        cooling_effect_c_per_hour: float = 0.45,
    ) -> None:
        self.weights = (weights or ScenarioWeights()).normalized()
        self.nominal_cooling_power_kw = max(
            0.0,
            nominal_cooling_power_kw,
        )
        self.cooling_effect_c_per_hour = max(
            0.0,
            cooling_effect_c_per_hour,
        )

    def evaluate(
        self,
        context: Mapping[str, Any],
    ) -> ScenarioDecision:
        blocking = bool(context.get("blocking", False))
        indoor = _number(
            _nested(
                context,
                "measurements",
                "indoor_temperature_c",
            )
        )
        target = _number(
            _nested(
                context,
                "configuration",
                "comfort_target_c",
            )
        )
        margin = _number(
            _nested(
                context,
                "configuration",
                "condensation_margin_c",
            )
        )
        minimum_margin = _number(
            _nested(
                context,
                "configuration",
                "minimum_condensation_margin_c",
            )
        )
        context_confidence = _number(
            _nested(
                context,
                "recommendation",
                "confidence",
            )
        ) or 0.0

        if indoor is None:
            indoor = 25.0

        if target is None:
            target = 24.0

        forecast_2h = _forecast_temperature(
            context,
            120,
        )

        if forecast_2h is None:
            forecast_2h = indoor

        safety_score, condensation_risk = self._safety_score(
            blocking=blocking,
            margin=margin,
            minimum_margin=minimum_margin,
        )

        results = tuple(
            self._evaluate_one(
                scenario=scenario,
                indoor=indoor,
                target=target,
                forecast_2h=forecast_2h,
                safety_score=safety_score,
                condensation_risk=condensation_risk,
                context_confidence=context_confidence,
            )
            for scenario in ScenarioName
        )

        ranked = tuple(
            sorted(
                results,
                key=lambda item: item.score,
                reverse=True,
            )
        )

        selected = ranked[0]
        explanation = self._explain_selection(
            selected=selected,
            alternatives=ranked[1:],
            indoor=indoor,
            target=target,
            forecast_2h=forecast_2h,
            condensation_risk=condensation_risk,
        )

        confidence = _clamp(
            (
                context_confidence * 0.7
                + selected.score * 0.3
            )
        )

        return ScenarioDecision(
            selected=selected,
            alternatives=ranked[1:],
            explanation=explanation,
            confidence=round(confidence, 3),
        )

    def _evaluate_one(
        self,
        *,
        scenario: ScenarioName,
        indoor: float,
        target: float,
        forecast_2h: float,
        safety_score: float,
        condensation_risk: str,
        context_confidence: float,
    ) -> ScenarioResult:
        runtime_minutes, delay_minutes, intensity = {
            ScenarioName.WAIT: (0, 120, 0.0),
            ScenarioName.PRECOOL_30: (60, 30, 0.75),
            ScenarioName.PRECOOL_60: (45, 60, 0.70),
            ScenarioName.COOL_NOW: (90, 0, 1.00),
            ScenarioName.SOFT_COOLING: (120, 0, 0.45),
        }[scenario]

        projected = forecast_2h

        if runtime_minutes > 0:
            effective_hours = runtime_minutes / 60.0
            cooling_gain = (
                self.cooling_effect_c_per_hour
                * effective_hours
                * intensity
            )
            projected -= cooling_gain

        delay_penalty = delay_minutes / 240.0
        comfort_error = abs(projected - target)
        comfort_score = _clamp(
            1.0 - comfort_error / 3.0 - delay_penalty * 0.15
        )

        energy_kwh = (
            self.nominal_cooling_power_kw
            * (runtime_minutes / 60.0)
            * intensity
        )
        energy_score = _clamp(
            1.0 - energy_kwh / 3.0
        )

        starts = 0 if runtime_minutes == 0 else 1
        stability_score = _clamp(
            1.0 - starts * 0.10 - abs(intensity - 0.65) * 0.20
        )

        learning_score = _clamp(context_confidence)

        if condensation_risk == "CRITICAL":
            scenario_safety = 0.0
        elif condensation_risk == "HIGH":
            scenario_safety = safety_score * (
                0.75 if intensity <= 0.5 else 0.40
            )
        else:
            scenario_safety = safety_score

        score = (
            comfort_score * self.weights.comfort
            + scenario_safety * self.weights.safety
            + energy_score * self.weights.energy
            + stability_score * self.weights.stability
            + learning_score * self.weights.learning
        )

        reasons = [
            f"Projected indoor temperature: {projected:.2f}°C",
            f"Estimated runtime: {runtime_minutes} min",
            f"Estimated energy: {energy_kwh:.2f} kWh",
            f"Condensation risk: {condensation_risk}",
        ]

        if scenario is ScenarioName.WAIT:
            reasons.append(
                "No active cooling; lowest energy use."
            )

        if scenario in {
            ScenarioName.PRECOOL_30,
            ScenarioName.PRECOOL_60,
        }:
            reasons.append(
                "Delayed start balances comfort and energy."
            )

        if scenario is ScenarioName.COOL_NOW:
            reasons.append(
                "Immediate cooling maximizes short-term comfort."
            )

        if scenario is ScenarioName.SOFT_COOLING:
            reasons.append(
                "Lower intensity improves stability and condensation margin."
            )

        return ScenarioResult(
            scenario=scenario,
            score=round(_clamp(score), 4),
            comfort_score=round(comfort_score, 4),
            safety_score=round(_clamp(scenario_safety), 4),
            energy_score=round(energy_score, 4),
            stability_score=round(stability_score, 4),
            learning_score=round(learning_score, 4),
            predicted_indoor_temperature_c=round(projected, 3),
            estimated_runtime_minutes=runtime_minutes,
            estimated_energy_kwh=round(energy_kwh, 3),
            condensation_risk=condensation_risk,
            reasons=tuple(reasons),
        )

    @staticmethod
    def _safety_score(
        *,
        blocking: bool,
        margin: float | None,
        minimum_margin: float | None,
    ) -> tuple[float, str]:
        if blocking:
            return 0.0, "CRITICAL"

        if margin is None or minimum_margin is None:
            return 0.55, "UNKNOWN"

        reserve = margin - minimum_margin

        if reserve < 0:
            return 0.0, "CRITICAL"

        if reserve < 0.5:
            return 0.35, "HIGH"

        if reserve < 1.5:
            return 0.70, "MEDIUM"

        return 1.0, "LOW"

    @staticmethod
    def _explain_selection(
        *,
        selected: ScenarioResult,
        alternatives: Sequence[ScenarioResult],
        indoor: float,
        target: float,
        forecast_2h: float,
        condensation_risk: str,
    ) -> tuple[str, ...]:
        explanation = [
            f"Selected {selected.scenario.value} with score {selected.score:.3f}.",
            f"Indoor temperature is {indoor:.2f}°C for a target of {target:.2f}°C.",
            f"Passive 2h forecast is {forecast_2h:.2f}°C.",
            f"Condensation risk is {condensation_risk}.",
        ]

        if alternatives:
            explanation.append(
                "Best alternative is "
                f"{alternatives[0].scenario.value} "
                f"with score {alternatives[0].score:.3f}."
            )

        return tuple(explanation)
