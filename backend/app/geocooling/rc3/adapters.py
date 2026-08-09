"""
GeoCooling RC3.1 — adapters from the existing Decision Context and
Scenario Engine to the frozen RC3 contracts.

All adapters are passive. They transform in-memory payloads only.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.geocooling.rc3.contracts import (
    ConstraintViolation,
    DecisionInput,
    DecisionMode,
    ForecastPoint,
    MeasurementSet,
    ScenarioScore,
    Severity,
)


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


def _mapping(value: Any) -> Mapping[str, Any]:
    return value if isinstance(value, Mapping) else {}


class LegacyDecisionContextAdapter:
    def from_payload(
        self,
        payload: Mapping[str, Any],
        *,
        mode: DecisionMode = DecisionMode.SHADOW,
    ) -> DecisionInput:
        measurements_payload = _mapping(
            payload.get("measurements")
        )
        configuration = dict(
            _mapping(payload.get("configuration"))
        )
        availability = {
            str(key): bool(value)
            for key, value in _mapping(
                payload.get("availability")
            ).items()
        }
        quality = {
            str(key): str(value)
            for key, value in _mapping(
                payload.get("quality")
            ).items()
        }

        forecasts: list[ForecastPoint] = []

        raw_forecasts = payload.get("forecasts")

        if isinstance(raw_forecasts, list):
            for item in raw_forecasts:
                if not isinstance(item, Mapping):
                    continue

                horizon = item.get("horizon_minutes")

                if not isinstance(horizon, int):
                    continue

                forecasts.append(
                    ForecastPoint(
                        horizon_minutes=horizon,
                        indoor_temperature_c=_number(
                            item.get(
                                "indoor_temperature_c"
                            )
                        ),
                        confidence=max(
                            0.0,
                            min(
                                1.0,
                                _number(
                                    item.get("confidence")
                                )
                                or 0.0,
                            ),
                        ),
                        source=str(
                            item.get("source")
                            or "legacy-decision-context"
                        ),
                    )
                )

        constraints: list[ConstraintViolation] = []

        raw_risks = payload.get("risks")

        if isinstance(raw_risks, list):
            for risk in raw_risks:
                if not isinstance(risk, Mapping):
                    continue

                severity_value = str(
                    risk.get("level") or "INFO"
                ).upper()

                try:
                    severity = Severity(severity_value)
                except ValueError:
                    severity = Severity.INFO

                constraints.append(
                    ConstraintViolation(
                        code=str(
                            risk.get("code")
                            or "UNKNOWN"
                        ),
                        severity=severity,
                        message=str(
                            risk.get("message")
                            or ""
                        ),
                        blocking=bool(
                            risk.get("blocking", False)
                        ),
                        value=_number(risk.get("value")),
                        threshold=_number(
                            risk.get("threshold")
                        ),
                    )
                )

        return DecisionInput(
            schema="geocooling.rc3.decision-input.v1",
            generated_at=str(
                payload.get("timestamp")
                or datetime.now(
                    timezone.utc
                ).isoformat()
            ),
            mode=mode,
            measurements=MeasurementSet(
                indoor_temperature_c=_number(
                    measurements_payload.get(
                        "indoor_temperature_c"
                    )
                ),
                indoor_humidity_pct=_number(
                    measurements_payload.get(
                        "indoor_humidity_pct"
                    )
                ),
                outdoor_temperature_c=_number(
                    measurements_payload.get(
                        "outdoor_temperature_c"
                    )
                ),
                dew_point_c=_number(
                    measurements_payload.get(
                        "dew_point_c"
                    )
                ),
                floor_surface_temperature_c=_number(
                    measurements_payload.get(
                        "floor_surface_temperature_c"
                    )
                ),
                floor_supply_temperature_c=_number(
                    measurements_payload.get(
                        "floor_supply_temperature_c"
                    )
                ),
                floor_return_temperature_c=_number(
                    measurements_payload.get(
                        "floor_return_temperature_c"
                    )
                ),
                source_in_temperature_c=_number(
                    measurements_payload.get(
                        "source_in_temperature_c"
                    )
                ),
                source_out_temperature_c=_number(
                    measurements_payload.get(
                        "source_out_temperature_c"
                    )
                ),
                flow_l_min=_number(
                    measurements_payload.get(
                        "flow_l_min"
                    )
                ),
            ),
            forecasts=tuple(forecasts),
            constraints=tuple(constraints),
            configuration=configuration,
            availability=availability,
            quality=quality,
            metadata={
                "adapter": "LegacyDecisionContextAdapter",
                "source_schema": payload.get("schema"),
                "legacy_recommendation": dict(
                    _mapping(
                        payload.get(
                            "recommendation"
                        )
                    )
                ),
            },
        )


class LegacyScenarioResultAdapter:
    def from_payload(
        self,
        payload: Mapping[str, Any],
    ) -> tuple[ScenarioScore, ...]:
        selected = _mapping(payload.get("selected"))
        alternatives = payload.get("alternatives")

        items: list[Mapping[str, Any]] = []

        if selected:
            items.append(selected)

        if isinstance(alternatives, list):
            items.extend(
                item
                for item in alternatives
                if isinstance(item, Mapping)
            )

        results: list[ScenarioScore] = []

        for item in items:
            results.append(
                ScenarioScore(
                    name=str(
                        item.get("scenario")
                        or "UNKNOWN"
                    ),
                    total_score=_number(
                        item.get("score")
                    )
                    or 0.0,
                    comfort_score=_number(
                        item.get("comfort_score")
                    )
                    or 0.0,
                    safety_score=_number(
                        item.get("safety_score")
                    )
                    or 0.0,
                    energy_score=_number(
                        item.get("energy_score")
                    )
                    or 0.0,
                    stability_score=_number(
                        item.get("stability_score")
                    )
                    or 0.0,
                    learning_score=_number(
                        item.get("learning_score")
                    )
                    or 0.0,
                    predicted_indoor_temperature_c=(
                        _number(
                            item.get(
                                "predicted_indoor_temperature_c"
                            )
                        )
                    ),
                    estimated_runtime_minutes=int(
                        _number(
                            item.get(
                                "estimated_runtime_minutes"
                            )
                        )
                        or 0
                    ),
                    estimated_energy_kwh=_number(
                        item.get(
                            "estimated_energy_kwh"
                        )
                    )
                    or 0.0,
                    reasons=tuple(
                        str(reason)
                        for reason in (
                            item.get("reasons")
                            if isinstance(
                                item.get("reasons"),
                                list,
                            )
                            else []
                        )
                    ),
                )
            )

        return tuple(results)
