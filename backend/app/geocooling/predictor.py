from __future__ import annotations
import functools

import math
import os
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class TemperaturePrediction:
    horizon_minutes: int
    temperature_c: float
    change_c: float

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True, slots=True)
class PredictionResult:
    available: bool
    generated_at: datetime
    current_temperature_c: float | None
    effective_trend_c_per_hour: float | None
    operating_state: str
    confidence: int
    method: str
    predictions: tuple[TemperaturePrediction, ...]
    reasons: tuple[str, ...]

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["generated_at"] = self.generated_at.isoformat()
        payload["predictions"] = [item.as_dict() for item in self.predictions]
        payload["reasons"] = list(self.reasons)
        return payload


class GeoCoolingPredictor:
    """Prévision thermique courte durée, déterministe et explicable.

    Le prédicteur privilégie les tendances réellement mesurées. Lorsque
    l'historique est insuffisant, il complète l'estimation avec un modèle simple
    fondé sur l'écart intérieur/extérieur et la puissance frigorifique disponible.
    Il ne pilote aucun relais.
    """

    def __init__(self) -> None:
        self.horizons_minutes = self._parse_horizons(
            os.getenv("GEOCOOLING_PREDICTION_HORIZONS_MIN", "30,60,120")
        )
        self.house_thermal_capacity_kwh_per_c = max(
            0.5,
            float(os.getenv("GEOCOOLING_HOUSE_THERMAL_CAPACITY_KWH_PER_C", "18.0")),
        )
        self.passive_exchange_rate_per_hour = max(
            0.0,
            float(os.getenv("GEOCOOLING_PASSIVE_EXCHANGE_RATE_PER_HOUR", "0.08")),
        )
        self.maximum_abs_trend_c_per_hour = max(
            0.2,
            float(os.getenv("GEOCOOLING_MAX_PREDICTION_TREND_C_PER_HOUR", "2.5")),
        )

    @staticmethod
    def _parse_horizons(raw: str) -> tuple[int, ...]:
        values: list[int] = []
        for token in raw.split(","):
            token = token.strip()
            if not token:
                continue
            try:
                value = int(token)
            except ValueError:
                continue
            if 1 <= value <= 1440:
                values.append(value)
        return tuple(sorted(set(values))) or (30, 60, 120)

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            number = float(value)
        except (TypeError, ValueError):
            return None
        return number if math.isfinite(number) else None

    @staticmethod
    def _clamp(value: float, minimum: float, maximum: float) -> float:
        return max(minimum, min(maximum, value))

    def _measured_trend(self, thermal: dict[str, Any]) -> tuple[float | None, int, list[str]]:
        trends = thermal.get("trends_c_per_hour") or {}
        candidates: list[tuple[float, float, str]] = []

        trend_5m = self._number(trends.get("indoor_5m"))
        trend_30m = self._number(trends.get("indoor_30m"))
        trend_120m = self._number(trends.get("indoor_120m"))

        if trend_5m is not None:
            candidates.append((trend_5m, 0.20, "tendance 5 min"))
        if trend_30m is not None:
            candidates.append((trend_30m, 0.50, "tendance 30 min"))
        if trend_120m is not None:
            candidates.append((trend_120m, 0.30, "tendance 120 min"))

        if not candidates:
            return None, 0, []

        total_weight = sum(weight for _, weight, _ in candidates)
        trend = sum(value * weight for value, weight, _ in candidates) / total_weight
        confidence = min(90, 35 + len(candidates) * 18)
        labels = ", ".join(label for _, _, label in candidates)
        return trend, confidence, [f"Prévision basée sur {labels}"]

    def _model_trend(
        self,
        thermal: dict[str, Any],
        state: str,
    ) -> tuple[float | None, list[str]]:
        latest = thermal.get("latest") or {}
        adaptive = thermal.get("adaptive_model") or {}

        indoor = self._number(
            latest.get("indoor_temperature_c")
        )
        outdoor = self._number(
            latest.get("outdoor_temperature_c")
        )
        power_kw = self._number(
            thermal.get("cooling_power_kw")
        )

        if indoor is None:
            return None, []

        adaptive_available = bool(
            adaptive.get("available", False)
        )
        adaptive_confidence = int(
            self._number(
                adaptive.get("confidence")
            )
            or 0
        )

        learned_exchange = self._number(
            adaptive.get(
                "passive_exchange_rate_per_hour"
            )
        )
        learned_capacity = self._number(
            adaptive.get(
                "house_thermal_capacity_kwh_per_c"
            )
        )
        learned_active_rate = self._number(
            adaptive.get(
                "active_cooling_rate_c_per_hour"
            )
        )

        exchange_rate = (
            learned_exchange
            if (
                adaptive_available
                and learned_exchange is not None
            )
            else self.passive_exchange_rate_per_hour
        )

        capacity = (
            learned_capacity
            if (
                adaptive_available
                and learned_capacity is not None
            )
            else self.house_thermal_capacity_kwh_per_c
        )

        passive = 0.0
        reasons: list[str] = []

        if outdoor is not None:
            passive = (
                outdoor
                - indoor
            ) * exchange_rate

            if (
                adaptive_available
                and learned_exchange is not None
            ):
                reasons.append(
                    "Échange passif issu du modèle "
                    f"adaptatif ({adaptive_confidence} %)"
                )
            else:
                reasons.append(
                    "Échange passif estimé avec "
                    f"extérieur à {outdoor:.1f} °C"
                )

        running = (
            state == "RUNNING"
            or bool(
                latest.get(
                    "pump_running",
                    False,
                )
            )
        )

        cooling = 0.0

        if running:
            if (
                adaptive_available
                and learned_active_rate is not None
                and adaptive_confidence >= 40
            ):
                cooling = max(
                    0.0,
                    learned_active_rate,
                )

                reasons.append(
                    "Effet GeoCooling appris "
                    f"({cooling:.3f} °C/h)"
                )

            elif power_kw is not None and power_kw > 0:
                cooling = power_kw / capacity

                if (
                    adaptive_available
                    and learned_capacity is not None
                ):
                    reasons.append(
                        "Capacité thermique apprise : "
                        f"{capacity:.2f} kWh/°C"
                    )
                else:
                    reasons.append(
                        "Effet du GeoCooling estimé "
                        f"avec {power_kw:.2f} kW"
                    )

        return passive - cooling, reasons

    def _c0124r1_original_predict(self, *, state: str, thermal: dict[str, Any]) -> PredictionResult:
        generated_at = utc_now()
        latest = thermal.get("latest") or {}
        indoor = self._number(latest.get("indoor_temperature_c"))

        if not thermal.get("available", False) or indoor is None:
            return PredictionResult(
                available=False,
                generated_at=generated_at,
                current_temperature_c=indoor,
                effective_trend_c_per_hour=None,
                operating_state=state,
                confidence=0,
                method="unavailable",
                predictions=(),
                reasons=("Température intérieure indisponible",),
            )

        measured, measured_confidence, measured_reasons = self._measured_trend(thermal)
        modelled, model_reasons = self._model_trend(thermal, state)

        if measured is not None and modelled is not None:
            measured_weight = 0.75
            effective = measured * measured_weight + modelled * (1.0 - measured_weight)
            confidence = min(95, measured_confidence + 5)
            method = "measured_trend_with_physical_correction"
            reasons = measured_reasons + model_reasons
        elif measured is not None:
            effective = measured
            confidence = measured_confidence
            method = "measured_trend"
            reasons = measured_reasons
        elif modelled is not None:
            effective = modelled
            confidence = 35
            method = "physical_fallback"
            reasons = model_reasons + ["Historique insuffisant : modèle physique simplifié"]
        else:
            return PredictionResult(
                available=False,
                generated_at=generated_at,
                current_temperature_c=indoor,
                effective_trend_c_per_hour=None,
                operating_state=state,
                confidence=0,
                method="unavailable",
                predictions=(),
                reasons=("Données insuffisantes pour établir une tendance",),
            )

        effective = self._clamp(
            effective,
            -self.maximum_abs_trend_c_per_hour,
            self.maximum_abs_trend_c_per_hour,
        )

        predictions = tuple(
            TemperaturePrediction(
                horizon_minutes=minutes,
                temperature_c=round(indoor + effective * minutes / 60.0, 2),
                change_c=round(effective * minutes / 60.0, 2),
            )
            for minutes in self.horizons_minutes
        )

        return PredictionResult(
            available=True,
            generated_at=generated_at,
            current_temperature_c=round(indoor, 2),
            effective_trend_c_per_hour=round(effective, 3),
            operating_state=state,
            confidence=confidence,
            method=method,
            predictions=predictions,
            reasons=tuple(reasons),
        )

    def configuration(self) -> dict[str, Any]:
        return {
            "horizons_minutes": list(self.horizons_minutes),
            "house_thermal_capacity_kwh_per_c": self.house_thermal_capacity_kwh_per_c,
            "passive_exchange_rate_per_hour": self.passive_exchange_rate_per_hour,
            "maximum_abs_trend_c_per_hour": self.maximum_abs_trend_c_per_hour,
            "advisory_only": True,
        }


    # PATCH C012.4R1 — Prediction Updated Publisher
    @staticmethod
    def _c0124r1_json_safe(value):
        """
        Convertit une valeur vers une structure sérialisable.
        """

        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        enum_value = getattr(value, "value", None)

        if isinstance(
            enum_value,
            (str, int, float, bool),
        ):
            return enum_value

        if isinstance(value, dict):
            return {
                str(key):
                    GeoCoolingPredictor
                    ._c0124r1_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(
            value,
            (list, tuple, set, frozenset),
        ):
            return [
                GeoCoolingPredictor
                ._c0124r1_json_safe(item)
                for item in value
            ]

        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass

        if hasattr(value, "__dict__"):
            try:
                return {
                    str(key):
                        GeoCoolingPredictor
                        ._c0124r1_json_safe(item)
                    for key, item in vars(value).items()
                    if not str(key).startswith("_")
                }
            except Exception:
                pass

        try:
            return str(value)
        except Exception:
            return f"<{type(value).__name__}>"

    @staticmethod
    def _c0124r1_extract(result, *names):
        """
        Extrait un champ depuis un dictionnaire ou un objet.
        """

        if isinstance(result, dict):
            for name in names:
                if name in result:
                    return result.get(name)

            return None

        for name in names:
            try:
                if hasattr(result, name):
                    return getattr(result, name)
            except Exception:
                continue

        return None

    def _c0124r1_event_payload(self, result):
        """
        Construit un payload générique sans dépendre
        du modèle exact de la prédiction.
        """

        payload = {
            "prediction": self._c0124r1_extract(
                result,
                "prediction",
                "forecast",
                "result",
                "value",
            ),
            "predicted_state": self._c0124r1_extract(
                result,
                "predicted_state",
                "state",
                "target_state",
            ),
            "predicted_mode": self._c0124r1_extract(
                result,
                "predicted_mode",
                "mode",
                "target_mode",
            ),
            "action": self._c0124r1_extract(
                result,
                "action",
                "recommended_action",
                "recommendation",
            ),
            "confidence": self._c0124r1_extract(
                result,
                "confidence",
                "confidence_score",
                "probability",
            ),
            "score": self._c0124r1_extract(
                result,
                "score",
                "prediction_score",
            ),
            "reason": self._c0124r1_extract(
                result,
                "reason",
                "reasoning",
                "explanation",
            ),
            "eta": self._c0124r1_extract(
                result,
                "eta",
                "estimated_time",
                "time_to_target",
            ),
            "temperature": self._c0124r1_extract(
                result,
                "temperature",
                "predicted_temperature",
                "target_temperature",
            ),
            "enabled": self._c0124r1_extract(
                result,
                "enabled",
                "active",
            ),
            "safe": self._c0124r1_extract(
                result,
                "safe",
                "is_safe",
                "safety_ok",
            ),
        }

        payload = {
            key: self._c0124r1_json_safe(value)
            for key, value in payload.items()
            if value is not None
        }

        if payload:
            return payload

        fallback = {
            "result_type": type(result).__name__,
        }

        if isinstance(result, dict):
            fallback["result_keys"] = sorted(
                str(key)
                for key in result.keys()
            )
        elif result is not None:
            fallback["result"] = (
                self._c0124r1_json_safe(result)
            )

        return fallback

    def _c0124r1_publish_prediction_updated(
        self,
        result,
    ):
        """
        Publie prediction.updated.

        Toute erreur du bus est neutralisée afin de ne jamais
        perturber le calcul du Predictor.
        """

        try:
            event_bus = getattr(
                self,
                "_event_bus",
                None,
            )

            if event_bus is None:
                controller = getattr(
                    self,
                    "controller",
                    None,
                )

                if controller is None:
                    controller = getattr(
                        self,
                        "_controller",
                        None,
                    )

                event_bus = getattr(
                    controller,
                    "event_bus",
                    None,
                )

            if event_bus is None:
                return None

            publish = getattr(
                event_bus,
                "publish",
                None,
            )

            if not callable(publish):
                return None

            payload = self._c0124r1_event_payload(
                result
            )

            try:
                return publish(
                    event_type="prediction.updated",
                    source="predictor",
                    payload=payload,
                    level="INFO",
                )
            except TypeError:
                try:
                    return publish(
                        "prediction.updated",
                        "predictor",
                        payload,
                        "INFO",
                    )
                except TypeError:
                    return publish(
                        "prediction.updated",
                        "predictor",
                        payload,
                    )

        except Exception:
            return None

    @functools.wraps(_c0124r1_original_predict)
    def predict(self, *args, **kwargs):
        """
        Exécute le calcul historique puis publie
        prediction.updated en cas de succès.
        """

        result = self._c0124r1_original_predict(
            *args,
            **kwargs,
        )

        self._c0124r1_publish_prediction_updated(
            result
        )

        return result
