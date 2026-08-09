"""
GeoCooling RC1.7B — passive DecisionContext builder.

The builder is intentionally defensive and read-only:
- it never writes to hardware;
- it never publishes MQTT;
- it never starts a service;
- it never mutates the database.

It accepts already available payloads and normalizes them into the canonical
DecisionContext introduced by RC1.7A.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Iterable, Mapping, Sequence

from app.geocooling.decision_context_v1 import (
    DataQuality,
    DecisionAction,
    DecisionContext,
    DecisionForecast,
    DecisionRisk,
    RiskLevel,
    build_decision_context,
)


@dataclass(frozen=True, slots=True)
class ContextSource:
    name: str
    payload: Mapping[str, Any] | None
    available: bool
    detail: str | None = None


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _walk(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, Sequence) and not isinstance(
        node,
        (str, bytes, bytearray),
    ):
        for value in node:
            yield from _walk(value)


def _first(
    payloads: Sequence[Mapping[str, Any] | None],
    keys: Sequence[str],
) -> Any:
    wanted = {key.lower() for key in keys}

    for payload in payloads:
        if not isinstance(payload, Mapping):
            continue

        for key, value in _walk(payload):
            if key.lower() in wanted and value is not None:
                return value

    return None


def _as_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if converted != converted:
        return None

    if converted in {float("inf"), float("-inf")}:
        return None

    return converted


def _as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {
            "true",
            "yes",
            "1",
            "on",
            "online",
            "available",
            "ready",
            "running",
            "connected",
            "open",
        }:
            return True

        if normalized in {
            "false",
            "no",
            "0",
            "off",
            "offline",
            "unavailable",
            "not_ready",
            "stopped",
            "disconnected",
            "closed",
        }:
            return False

    return None


def _quality_from_availability(
    *,
    available: bool,
    payload: Mapping[str, Any] | None,
    required_values: Sequence[Any] = (),
) -> DataQuality:
    if not available:
        return DataQuality.INSUFFICIENT

    if payload is None:
        return DataQuality.DEGRADED

    if required_values and any(value is None for value in required_values):
        return DataQuality.DEGRADED

    return DataQuality.GOOD


def _risk(
    code: str,
    level: RiskLevel,
    message: str,
    *,
    blocking: bool = False,
    value: float | None = None,
    threshold: float | None = None,
) -> DecisionRisk:
    return DecisionRisk(
        code=code,
        level=level,
        message=message,
        blocking=blocking,
        value=value,
        threshold=threshold,
    )


class PassiveDecisionContextBuilder:
    """
    Normalize existing payloads into one passive DecisionContext.

    The builder does not call application services directly. This keeps it
    deterministic, testable and safe. The API adapter can supply snapshots
    obtained from the already existing read-only services.
    """

    def build(
        self,
        *,
        thermal: Mapping[str, Any] | None = None,
        weather: Mapping[str, Any] | None = None,
        prediction: Mapping[str, Any] | None = None,
        learning: Mapping[str, Any] | None = None,
        historian: Mapping[str, Any] | None = None,
        hardware: Mapping[str, Any] | None = None,
        runtime: Mapping[str, Any] | None = None,
        configuration: Mapping[str, Any] | None = None,
        timestamp: str | None = None,
    ) -> DecisionContext:
        configuration = configuration or {}

        thermal_payloads = [thermal, runtime]
        weather_payloads = [weather]
        prediction_payloads = [prediction]
        learning_payloads = [learning]
        hardware_payloads = [hardware, runtime]

        indoor_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "indoor_temperature",
                    "indoor_temperature_c",
                    "inside_temperature",
                    "room_temperature",
                ),
            )
        )
        indoor_humidity = _as_float(
            _first(
                thermal_payloads,
                (
                    "indoor_humidity",
                    "indoor_humidity_pct",
                    "inside_humidity",
                    "relative_humidity",
                    "humidity",
                ),
            )
        )
        outdoor_temperature = _as_float(
            _first(
                weather_payloads + thermal_payloads,
                (
                    "outdoor_temperature",
                    "outdoor_temperature_c",
                    "outside_temperature",
                    "current_temperature",
                    "temperature_2m",
                ),
            )
        )
        dew_point = _as_float(
            _first(
                thermal_payloads,
                (
                    "dew_point",
                    "dew_point_c",
                    "point_de_rosee",
                ),
            )
        )
        floor_surface_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "floor_surface_temperature",
                    "floor_surface_temperature_c",
                    "surface_temperature",
                ),
            )
        )
        floor_supply_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "floor_supply",
                    "floor_supply_temperature",
                    "floor_supply_temperature_c",
                    "supply_temperature",
                    "departure_temperature",
                    "depart_temperature",
                ),
            )
        )
        floor_return_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "floor_return",
                    "floor_return_temperature",
                    "floor_return_temperature_c",
                    "return_temperature",
                    "retour_temperature",
                ),
            )
        )
        source_in_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "source_in",
                    "source_in_temperature",
                    "source_in_temperature_c",
                    "source_inlet_temperature",
                ),
            )
        )
        source_out_temperature = _as_float(
            _first(
                thermal_payloads,
                (
                    "source_out",
                    "source_out_temperature",
                    "source_out_temperature_c",
                    "source_outlet_temperature",
                ),
            )
        )
        flow = _as_float(
            _first(
                thermal_payloads,
                (
                    "flow_l_min",
                    "flow_rate",
                    "flow",
                ),
            )
        )

        comfort_target = _as_float(
            configuration.get(
                "comfort_target_c",
                _first(
                    thermal_payloads,
                    ("comfort_target", "comfort_target_c"),
                ),
            )
        )
        cooling_start_threshold = _as_float(
            configuration.get(
                "cooling_start_threshold_c",
                _first(
                    thermal_payloads,
                    (
                        "cooling_start_threshold",
                        "cooling_start_threshold_c",
                    ),
                ),
            )
        )
        cooling_stop_threshold = _as_float(
            configuration.get(
                "cooling_stop_threshold_c",
                _first(
                    thermal_payloads,
                    (
                        "cooling_stop_threshold",
                        "cooling_stop_threshold_c",
                    ),
                ),
            )
        )
        condensation_margin = _as_float(
            _first(
                thermal_payloads,
                (
                    "condensation_margin",
                    "condensation_margin_c",
                    "dew_point_margin",
                ),
            )
        )
        minimum_condensation_margin = _as_float(
            configuration.get(
                "minimum_condensation_margin_c",
                _first(
                    thermal_payloads,
                    (
                        "minimum_condensation_margin",
                        "minimum_condensation_margin_c",
                        "min_condensation_margin",
                    ),
                ),
            )
        )

        weather_available = weather is not None
        historian_available = historian is not None
        learning_available = learning is not None
        prediction_available = prediction is not None

        hardware_available_value = _as_bool(
            _first(
                hardware_payloads,
                (
                    "ready",
                    "hardware_ready",
                    "available",
                    "device_online",
                    "connected",
                ),
            )
        )
        hardware_available = bool(hardware_available_value)

        forecasts = self._build_forecasts(prediction)

        risks: list[DecisionRisk] = []
        reasons: list[str] = []

        if indoor_temperature is None:
            risks.append(
                _risk(
                    "INDOOR_TEMPERATURE_MISSING",
                    RiskLevel.CRITICAL,
                    "Indoor temperature is unavailable.",
                    blocking=True,
                )
            )

        if indoor_humidity is None:
            risks.append(
                _risk(
                    "INDOOR_HUMIDITY_MISSING",
                    RiskLevel.HIGH,
                    "Indoor humidity is unavailable.",
                    blocking=True,
                )
            )

        if not weather_available:
            risks.append(
                _risk(
                    "WEATHER_UNAVAILABLE",
                    RiskLevel.MEDIUM,
                    "Weather payload is unavailable.",
                )
            )

        if not historian_available:
            risks.append(
                _risk(
                    "HISTORIAN_UNAVAILABLE",
                    RiskLevel.MEDIUM,
                    "Historian payload is unavailable.",
                )
            )

        if not learning_available:
            risks.append(
                _risk(
                    "LEARNING_UNAVAILABLE",
                    RiskLevel.LOW,
                    "Learning payload is unavailable; passive mode continues.",
                )
            )

        if not prediction_available:
            risks.append(
                _risk(
                    "PREDICTION_UNAVAILABLE",
                    RiskLevel.MEDIUM,
                    "Prediction payload is unavailable.",
                )
            )

        if not hardware_available:
            risks.append(
                _risk(
                    "HARDWARE_UNAVAILABLE",
                    RiskLevel.MEDIUM,
                    "Hardware is unavailable or intentionally disconnected.",
                )
            )

        if (
            condensation_margin is not None
            and minimum_condensation_margin is not None
            and condensation_margin < minimum_condensation_margin
        ):
            risks.append(
                _risk(
                    "CONDENSATION_MARGIN_LOW",
                    RiskLevel.CRITICAL,
                    "Condensation margin is below the configured minimum.",
                    blocking=True,
                    value=condensation_margin,
                    threshold=minimum_condensation_margin,
                )
            )

        if indoor_temperature is not None and comfort_target is not None:
            if indoor_temperature > comfort_target:
                reasons.append(
                    "Indoor temperature is above the comfort target."
                )
            else:
                reasons.append(
                    "Indoor temperature is at or below the comfort target."
                )

        if forecasts:
            reasons.append(
                f"{len(forecasts)} thermal forecast horizon(s) available."
            )

        action = DecisionAction.WAIT

        if any(risk.blocking for risk in risks):
            action = DecisionAction.BLOCKED
        elif (
            indoor_temperature is not None
            and cooling_start_threshold is not None
            and indoor_temperature >= cooling_start_threshold
            and hardware_available
        ):
            action = DecisionAction.START_COOLING
        elif (
            indoor_temperature is not None
            and cooling_stop_threshold is not None
            and indoor_temperature <= cooling_stop_threshold
        ):
            action = DecisionAction.STOP_COOLING

        confidence = self._confidence(
            sensor_quality=_quality_from_availability(
                available=thermal is not None,
                payload=thermal,
                required_values=(indoor_temperature, indoor_humidity),
            ),
            weather_quality=_quality_from_availability(
                available=weather_available,
                payload=weather,
                required_values=(outdoor_temperature,),
            ),
            historian_available=historian_available,
            learning_available=learning_available,
            prediction_available=prediction_available,
        )

        inertia = _first(
            learning_payloads + thermal_payloads,
            (
                "building_inertia",
                "thermal_inertia",
                "inertia",
                "inertia_class",
            ),
        )

        return build_decision_context(
            timestamp=timestamp or _utc_now_iso(),
            measurements={
                "indoor_temperature_c": indoor_temperature,
                "indoor_humidity_pct": indoor_humidity,
                "outdoor_temperature_c": outdoor_temperature,
                "dew_point_c": dew_point,
                "floor_surface_temperature_c": floor_surface_temperature,
                "floor_supply_temperature_c": floor_supply_temperature,
                "floor_return_temperature_c": floor_return_temperature,
                "source_in_temperature_c": source_in_temperature,
                "source_out_temperature_c": source_out_temperature,
                "flow_l_min": flow,
            },
            configuration={
                "comfort_target_c": comfort_target,
                "cooling_start_threshold_c": cooling_start_threshold,
                "cooling_stop_threshold_c": cooling_stop_threshold,
                "condensation_margin_c": condensation_margin,
                "minimum_condensation_margin_c": (
                    minimum_condensation_margin
                ),
                "building_inertia": inertia,
            },
            availability={
                "weather": weather_available,
                "historian": historian_available,
                "learning": learning_available,
                "prediction": prediction_available,
                "hardware": hardware_available,
            },
            quality={
                "sensors": _quality_from_availability(
                    available=thermal is not None,
                    payload=thermal,
                    required_values=(indoor_temperature, indoor_humidity),
                ),
                "weather": _quality_from_availability(
                    available=weather_available,
                    payload=weather,
                    required_values=(outdoor_temperature,),
                ),
                "learning": _quality_from_availability(
                    available=learning_available,
                    payload=learning,
                ),
                "prediction": _quality_from_availability(
                    available=prediction_available,
                    payload=prediction,
                    required_values=(forecasts[0] if forecasts else None,),
                ),
            },
            forecasts=forecasts,
            risks=risks,
            reasons=reasons,
            recommendation={
                "action": action,
                "confidence": confidence,
            },
            metadata={
                "builder": "PassiveDecisionContextBuilder",
                "patch": "RC1.7B",
                "mode": "passive",
                "source_presence": {
                    "thermal": thermal is not None,
                    "weather": weather is not None,
                    "prediction": prediction is not None,
                    "learning": learning is not None,
                    "historian": historian is not None,
                    "hardware": hardware is not None,
                    "runtime": runtime is not None,
                },
            },
        )

    def _build_forecasts(
        self,
        prediction: Mapping[str, Any] | None,
    ) -> tuple[DecisionForecast, ...]:
        if prediction is None:
            return ()

        result: list[DecisionForecast] = []

        horizon_keys = (
            (30, ("temperature_30m", "predicted_temperature_30m")),
            (60, ("temperature_1h", "predicted_temperature_1h")),
            (120, ("temperature_2h", "predicted_temperature_2h")),
            (240, ("temperature_4h", "predicted_temperature_4h")),
            (480, ("temperature_8h", "predicted_temperature_8h")),
            (1440, ("temperature_24h", "predicted_temperature_24h")),
        )

        general_confidence = _as_float(
            _first(
                [prediction],
                (
                    "confidence",
                    "prediction_confidence",
                ),
            )
        )

        for horizon_minutes, keys in horizon_keys:
            value = _as_float(_first([prediction], keys))

            if value is None:
                continue

            result.append(
                DecisionForecast(
                    horizon_minutes=horizon_minutes,
                    indoor_temperature_c=value,
                    confidence=general_confidence,
                    source="prediction_payload",
                )
            )

        if not result:
            generic = _as_float(
                _first(
                    [prediction],
                    (
                        "predicted_temperature",
                        "predicted_indoor_temperature",
                        "temperature_prediction",
                    ),
                )
            )

            if generic is not None:
                horizon = _as_float(
                    _first(
                        [prediction],
                        (
                            "horizon_minutes",
                            "prediction_horizon_minutes",
                        ),
                    )
                )

                result.append(
                    DecisionForecast(
                        horizon_minutes=int(horizon or 120),
                        indoor_temperature_c=generic,
                        confidence=general_confidence,
                        source="prediction_payload",
                    )
                )

        return tuple(result)

    @staticmethod
    def _confidence(
        *,
        sensor_quality: DataQuality,
        weather_quality: DataQuality,
        historian_available: bool,
        learning_available: bool,
        prediction_available: bool,
    ) -> float:
        quality_score = {
            DataQuality.GOOD: 1.0,
            DataQuality.DEGRADED: 0.55,
            DataQuality.INSUFFICIENT: 0.0,
            DataQuality.UNKNOWN: 0.25,
        }

        weighted = (
            quality_score[sensor_quality] * 0.40
            + quality_score[weather_quality] * 0.20
            + (1.0 if historian_available else 0.0) * 0.15
            + (1.0 if learning_available else 0.0) * 0.10
            + (1.0 if prediction_available else 0.0) * 0.15
        )

        return round(max(0.0, min(1.0, weighted)), 3)
