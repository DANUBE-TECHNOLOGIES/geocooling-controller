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
class BrainDecision:
    decision: str
    confidence: int
    comfort_score: int
    cooling_score: int
    risk_score: int
    total_score: int
    reason: tuple[str, ...]
    data_quality: int
    operating_mode: str
    recommended_runtime_minutes: int
    predicted_temperature_1h_c: float | None
    predicted_temperature_3h_c: float | None
    predicted_temperature_6h_c: float | None
    generated_at: datetime

    def as_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["reason"] = list(self.reason)
        payload["generated_at"] = self.generated_at.isoformat()
        return payload


class GeoCoolingBrain:
    """Moteur de décision consultatif pour le GeoCooling.

    Le moteur ne commande pas directement les relais. Il transforme le dernier
    état thermique et les sécurités en une recommandation explicable :
    START, MAINTAIN, STOP, WAIT ou BLOCKED.
    """

    def __init__(self) -> None:
        self.comfort_target_c = float(
            os.getenv("GEOCOOLING_COMFORT_TARGET_C", "24.0")
        )
        self.start_temperature_c = float(
            os.getenv("GEOCOOLING_START_TEMPERATURE_C", "25.0")
        )
        self.stop_temperature_c = float(
            os.getenv("GEOCOOLING_STOP_TEMPERATURE_C", "23.8")
        )
        self.minimum_cooling_power_kw = max(
            0.0,
            float(os.getenv("GEOCOOLING_MIN_USEFUL_POWER_KW", "0.8")),
        )
        self.minimum_safe_margin_c = max(
            0.0,
            float(os.getenv("GEOCOOLING_MIN_DEW_POINT_MARGIN_C", "3.0")),
        )

    @staticmethod
    def _number(value: Any) -> float | None:
        if value is None:
            return None
        try:
            result = float(value)
        except (TypeError, ValueError):
            return None
        return result if math.isfinite(result) else None

    @staticmethod
    def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> int:
        return int(round(max(minimum, min(maximum, value))))

    def _comfort_score(self, latest: dict[str, Any]) -> tuple[int, list[str]]:
        reasons: list[str] = []
        indoor = self._number(latest.get("indoor_temperature_c"))
        humidity = self._number(latest.get("indoor_humidity_percent"))
        outdoor = self._number(latest.get("outdoor_temperature_c"))

        if indoor is None:
            return 0, ["Température intérieure indisponible"]

        # Besoin de froid : 0 sous la consigne, 100 à consigne + 4 °C.
        temperature_need = self._clamp(
            (indoor - self.comfort_target_c) / 4.0 * 100.0
        )
        score = temperature_need * 0.70

        if indoor >= self.start_temperature_c:
            reasons.append(f"Maison chaude ({indoor:.1f} °C)")
        elif indoor <= self.stop_temperature_c:
            reasons.append(f"Consigne de confort atteinte ({indoor:.1f} °C)")
        else:
            reasons.append(f"Température proche de la consigne ({indoor:.1f} °C)")

        if humidity is not None:
            humidity_need = self._clamp((humidity - 50.0) / 30.0 * 100.0)
            score += humidity_need * 0.15
            if humidity >= 65.0:
                reasons.append(f"Humidité intérieure élevée ({humidity:.0f} %)")

        if outdoor is not None:
            outdoor_need = self._clamp((outdoor - 24.0) / 12.0 * 100.0)
            score += outdoor_need * 0.15
            if outdoor >= 30.0:
                reasons.append(f"Forte chaleur extérieure ({outdoor:.1f} °C)")

        return self._clamp(score), reasons

    def _cooling_score(self, thermal: dict[str, Any]) -> tuple[int, list[str]]:
        reasons: list[str] = []
        latest = thermal.get("latest") or {}
        score = 0.0
        available_weight = 0.0

        power = self._number(thermal.get("cooling_power_kw"))
        if power is not None:
            available_weight += 45.0
            score += min(45.0, max(0.0, power / 8.0 * 45.0))
            reasons.append(f"Puissance frigorifique estimée à {power:.2f} kW")

        floor_delta = self._number(thermal.get("floor_delta_t_c"))
        if floor_delta is not None:
            available_weight += 20.0
            score += min(20.0, max(0.0, floor_delta / 4.0 * 20.0))
            if floor_delta > 0:
                reasons.append(f"Échange plancher actif (ΔT {floor_delta:.2f} °C)")

        source_inlet = self._number(latest.get("source_inlet_temperature_c"))
        if source_inlet is not None:
            available_weight += 20.0
            score += self._clamp((20.0 - source_inlet) / 10.0 * 20.0, 0, 20)
            reasons.append(f"Source à {source_inlet:.1f} °C")

        flow = self._number(latest.get("flow_rate_l_min"))
        if flow is not None:
            available_weight += 15.0
            score += min(15.0, max(0.0, flow / 20.0 * 15.0))
            if flow > 0:
                reasons.append(f"Débit mesuré à {flow:.1f} l/min")

        if available_weight == 0:
            return 0, ["Capacité de refroidissement non mesurable"]

        # Normalise les données disponibles sur 100 sans pénaliser les capteurs absents.
        return self._clamp(score / available_weight * 100.0), reasons

    def _risk_score(
        self,
        safety: dict[str, Any],
        device: dict[str, Any],
        thermal: dict[str, Any],
    ) -> tuple[int, list[str]]:
        score = 0.0
        reasons: list[str] = []

        if not safety.get("safe", False):
            score += 100.0
            reasons.append(str(safety.get("reason") or "Sécurité thermique bloquante"))
        else:
            margin = self._number(safety.get("margin_c"))
            if margin is not None:
                if margin < self.minimum_safe_margin_c:
                    score += 80.0
                    reasons.append(f"Marge anti-condensation insuffisante ({margin:.2f} °C)")
                elif margin < self.minimum_safe_margin_c + 1.0:
                    score += 35.0
                    reasons.append(f"Marge anti-condensation faible ({margin:.2f} °C)")
                else:
                    reasons.append(f"Marge anti-condensation correcte ({margin:.2f} °C)")

        if not device.get("ready", False):
            score += 100.0
            reasons.append(str(device.get("reason") or "Équipement indisponible"))

        latest = thermal.get("latest") or {}
        pump_running = bool(latest.get("pump_running", False))
        flow = self._number(latest.get("flow_rate_l_min"))
        if pump_running and flow is not None and flow <= 0:
            score += 70.0
            reasons.append("Circulateur déclaré en marche sans débit")

        indoor_trend = self._number(
            (thermal.get("trends_c_per_hour") or {}).get("indoor_30m")
        )
        if pump_running and indoor_trend is not None and indoor_trend > 0.3:
            score += 20.0
            reasons.append("La température intérieure augmente malgré le refroidissement")

        return self._clamp(score), reasons

    def _c0123r4_original_evaluate(
        self,
        *,
        state: str,
        thermal: dict[str, Any],
        safety: dict[str, Any],
        device: dict[str, Any],
        anti_short_cycle: dict[str, Any] | None = None,
        prediction: dict[str, Any] | None = None,
    ) -> BrainDecision:
        anti_short_cycle = anti_short_cycle or {}
        prediction = prediction or {}
        latest = thermal.get("latest") or {}


        prediction_by_horizon: dict[int, float] = {}
        for item in prediction.get("predictions") or []:
            try:
                horizon = int(item.get("horizon_minutes"))
                temperature = self._number(item.get("temperature_c"))
            except (TypeError, ValueError, AttributeError):
                continue
            if temperature is not None:
                prediction_by_horizon[horizon] = temperature

        predicted_1h = prediction_by_horizon.get(60)
        predicted_3h = prediction_by_horizon.get(180)
        predicted_6h = prediction_by_horizon.get(360)

        required_fields = (
            latest.get("indoor_temperature_c"),
            latest.get("indoor_humidity_percent"),
            latest.get("outdoor_temperature_c"),
        )
        optional_fields = (
            latest.get("surface_temperature_c"),
            latest.get("floor_supply_temperature_c"),
            latest.get("floor_return_temperature_c"),
            latest.get("source_inlet_temperature_c"),
            latest.get("source_outlet_temperature_c"),
            latest.get("flow_rate_l_min"),
        )
        required_available = sum(self._number(value) is not None for value in required_fields)
        optional_available = sum(self._number(value) is not None for value in optional_fields)
        data_quality = self._clamp(
            required_available / len(required_fields) * 70.0
            + optional_available / len(optional_fields) * 30.0
        )
        operating_mode = "FULL" if optional_available >= 4 else "DEGRADED"

        comfort_score, comfort_reasons = self._comfort_score(latest)
        cooling_score, cooling_reasons = self._cooling_score(thermal)
        risk_score, risk_reasons = self._risk_score(safety, device, thermal)

        running = state == "RUNNING"
        remaining_off = int(anti_short_cycle.get("remaining_minimum_off_seconds") or 0)
        remaining_on = int(anti_short_cycle.get("remaining_minimum_on_seconds") or 0)

        total_score = self._clamp(
            comfort_score * 0.60 + cooling_score * 0.40 - risk_score * 0.80,
            -100,
            100,
        )
        reasons = comfort_reasons + cooling_reasons + risk_reasons

        if risk_score >= 80 or not safety.get("safe", False) or not device.get("ready", False):
            decision = "BLOCKED"
            confidence = max(90, risk_score)
        elif not thermal.get("available", False):
            decision = "WAIT"
            confidence = 100
            reasons.append("Aucune mesure thermique exploitable")
        elif running:
            indoor = self._number(latest.get("indoor_temperature_c"))
            power = self._number(thermal.get("cooling_power_kw"))
            if remaining_on > 0:
                decision = "MAINTAIN"
                confidence = 95
                reasons.append(
                    f"Durée minimale de marche : {remaining_on} seconde(s) restantes"
                )
            elif indoor is not None and indoor <= self.stop_temperature_c:
                decision = "STOP"
                confidence = self._clamp(70 + (self.stop_temperature_c - indoor) * 15)
            elif power is not None and power < self.minimum_cooling_power_kw:
                decision = "STOP"
                confidence = 75
                reasons.append("Puissance frigorifique devenue insuffisante")
            else:
                decision = "MAINTAIN"
                confidence = self._clamp(55 + comfort_score * 0.35 + cooling_score * 0.10)
        else:
            indoor = self._number(latest.get("indoor_temperature_c"))
            if remaining_off > 0:
                decision = "WAIT"
                confidence = 95
                reasons.append(
                    f"Anti-court-cycle : {remaining_off} seconde(s) restantes"
                )
            elif (
                indoor is not None
                and total_score >= 35
                and (
                    indoor >= self.start_temperature_c
                    or (predicted_3h is not None and predicted_3h >= self.start_temperature_c)
                )
            ):
                decision = "START"
                confidence = self._clamp(50 + total_score * 0.5)
                if indoor < self.start_temperature_c and predicted_3h is not None:
                    reasons.append(
                        f"Démarrage anticipé : {predicted_3h:.1f} °C prévus dans 3 h"
                    )
            else:
                decision = "WAIT"
                confidence = self._clamp(55 + max(0, 35 - total_score))

        if decision in {"START", "MAINTAIN"}:
            recommended_runtime_minutes = max(30, min(180, int(round(30 + comfort_score * 1.2))))
        else:
            recommended_runtime_minutes = 0

        if operating_mode == "DEGRADED":
            reasons.append("Mode dégradé : sondes hydrauliques incomplètes")

        # Déduplication stable pour garder une réponse lisible.
        unique_reasons = tuple(dict.fromkeys(reason for reason in reasons if reason))
        return BrainDecision(
            decision=decision,
            confidence=self._clamp(confidence),
            comfort_score=comfort_score,
            cooling_score=cooling_score,
            risk_score=risk_score,
            total_score=total_score,
            reason=unique_reasons,
            data_quality=data_quality,
            operating_mode=operating_mode,
            recommended_runtime_minutes=recommended_runtime_minutes,
            predicted_temperature_1h_c=predicted_1h,
            predicted_temperature_3h_c=predicted_3h,
            predicted_temperature_6h_c=predicted_6h,
            generated_at=utc_now(),
        )

    def configuration(self) -> dict[str, Any]:
        return {
            "comfort_target_c": self.comfort_target_c,
            "start_temperature_c": self.start_temperature_c,
            "stop_temperature_c": self.stop_temperature_c,
            "minimum_cooling_power_kw": self.minimum_cooling_power_kw,
            "minimum_safe_margin_c": self.minimum_safe_margin_c,
            "advisory_only": True,
        }


    # PATCH C012.3R4 — Brain Decision Publisher
    @staticmethod
    def _c0123r4_json_safe(value):
        if value is None:
            return None

        if isinstance(value, (str, int, float, bool)):
            return value

        enum_value = getattr(value, "value", None)

        if isinstance(enum_value, (str, int, float, bool)):
            return enum_value

        if isinstance(value, dict):
            return {
                str(key): GeoCoolingBrain._c0123r4_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set, frozenset)):
            return [
                GeoCoolingBrain._c0123r4_json_safe(item)
                for item in value
            ]

        if hasattr(value, "isoformat"):
            try:
                return value.isoformat()
            except Exception:
                pass

        try:
            return str(value)
        except Exception:
            return f"<{type(value).__name__}>"

    @staticmethod
    def _c0123r4_extract(result, *names):
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

    def _c0123r4_payload(self, result):
        payload = {
            "decision": self._c0123r4_extract(
                result,
                "decision",
                "recommendation",
                "requested_action",
            ),
            "action": self._c0123r4_extract(
                result,
                "action",
                "decision",
                "recommendation",
            ),
            "mode": self._c0123r4_extract(
                result,
                "mode",
                "target_mode",
                "requested_mode",
            ),
            "state": self._c0123r4_extract(
                result,
                "state",
                "current_state",
                "target_state",
            ),
            "reason": self._c0123r4_extract(
                result,
                "reason",
                "reasoning",
                "explanation",
            ),
            "confidence": self._c0123r4_extract(
                result,
                "confidence",
                "confidence_score",
            ),
            "score": self._c0123r4_extract(
                result,
                "score",
                "decision_score",
            ),
            "safe": self._c0123r4_extract(
                result,
                "safe",
                "is_safe",
                "safety_ok",
            ),
            "enabled": self._c0123r4_extract(
                result,
                "enabled",
                "active",
            ),
        }

        payload = {
            key: self._c0123r4_json_safe(value)
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
                self._c0123r4_json_safe(result)
            )

        return fallback

    def _c0123r4_publish_brain_decision(self, result):
        """
        Publie brain.decision sans jamais bloquer le Brain.
        """

        try:
            event_bus = getattr(self, "_event_bus", None)

            if event_bus is None:
                controller = getattr(self, "controller", None)

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

            publish = getattr(event_bus, "publish", None)

            if not callable(publish):
                return None

            payload = self._c0123r4_payload(result)

            try:
                return publish(
                    event_type="brain.decision",
                    source="brain",
                    payload=payload,
                    level="INFO",
                )
            except TypeError:
                try:
                    return publish(
                        "brain.decision",
                        "brain",
                        payload,
                        "INFO",
                    )
                except TypeError:
                    return publish(
                        "brain.decision",
                        "brain",
                        payload,
                    )

        except Exception:
            return None

    @functools.wraps(_c0123r4_original_evaluate)
    def evaluate(self, *args, **kwargs):
        """
        Exécute evaluate() historique puis publie brain.decision.
        """

        result = self._c0123r4_original_evaluate(
            *args,
            **kwargs,
        )

        self._c0123r4_publish_brain_decision(result)

        return result
