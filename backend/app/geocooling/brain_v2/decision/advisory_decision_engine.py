from __future__ import annotations

import json
import math
import os

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.geocooling.brain_v2.prediction.thermal_prediction_engine import (
    ThermalPredictionEngine,
)


class AdvisoryDecisionEngine:
    VERSION = "C022.5-ADVISORY-DECISION-1.0"

    DEFAULT_COMFORT_TARGET_C = 24.0
    DEFAULT_START_THRESHOLD_C = 25.0
    DEFAULT_STOP_THRESHOLD_C = 23.8
    DEFAULT_MINIMUM_CONFIDENCE_PERCENT = 20.0
    DEFAULT_MINIMUM_BENEFIT_C = 0.30
    DEFAULT_HORIZON_MINUTES = 360

    def __init__(
        self,
        data_directory: str | Path | None = None,
    ) -> None:
        configured_directory = (
            data_directory
            or os.getenv(
                "GEOCOOLING_BRAIN_V2_DATA_DIR",
                "/app/data/geocooling/brain_v2",
            )
        )

        self.data_directory = Path(
            configured_directory
        )

        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.prediction_engine = (
            ThermalPredictionEngine(
                data_directory=self.data_directory
            )
        )

        self.observations_path = (
            self.data_directory
            / "observations.jsonl"
        )

        self.decision_path = (
            self.data_directory
            / "advisory-decision.json"
        )

        self.history_path = (
            self.data_directory
            / "advisory-decisions.jsonl"
        )

        self.comfort_target_c = float(
            os.getenv(
                "GEOCOOLING_COMFORT_TARGET_C",
                str(
                    self.DEFAULT_COMFORT_TARGET_C
                ),
            )
        )

        self.start_threshold_c = float(
            os.getenv(
                "GEOCOOLING_START_THRESHOLD_C",
                str(
                    self.DEFAULT_START_THRESHOLD_C
                ),
            )
        )

        self.stop_threshold_c = float(
            os.getenv(
                "GEOCOOLING_STOP_THRESHOLD_C",
                str(
                    self.DEFAULT_STOP_THRESHOLD_C
                ),
            )
        )

        self.minimum_confidence_percent = float(
            os.getenv(
                "GEOCOOLING_DECISION_MIN_CONFIDENCE_PERCENT",
                str(
                    self.DEFAULT_MINIMUM_CONFIDENCE_PERCENT
                ),
            )
        )

        self.minimum_benefit_c = float(
            os.getenv(
                "GEOCOOLING_DECISION_MIN_BENEFIT_C",
                str(
                    self.DEFAULT_MINIMUM_BENEFIT_C
                ),
            )
        )

        self.horizon_minutes = int(
            os.getenv(
                "GEOCOOLING_DECISION_HORIZON_MINUTES",
                str(
                    self.DEFAULT_HORIZON_MINUTES
                ),
            )
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _as_float(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(
            value,
            bool,
        ):
            return None

        if isinstance(value, dict):
            for key in (
                "value",
                "state",
                "temperature",
                "reading",
            ):
                if key in value:
                    return AdvisoryDecisionEngine._as_float(
                        value[key]
                    )

            return None

        if isinstance(value, str):
            cleaned = (
                value.strip()
                .replace(",", ".")
                .replace("°C", "")
                .replace("%", "")
            )

            try:
                value = float(cleaned)
            except ValueError:
                return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(result):
            return None

        return result

    @staticmethod
    def _as_bool(
        value: Any,
    ) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value != 0

        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in {
                "1",
                "true",
                "yes",
                "on",
                "active",
                "running",
                "open",
            }:
                return True

            if normalized in {
                "0",
                "false",
                "no",
                "off",
                "inactive",
                "stopped",
                "closed",
            }:
                return False

        return None

    def _latest_observation(
        self,
    ) -> dict[str, Any]:
        if not self.observations_path.exists():
            return {}

        try:
            lines = (
                self.observations_path
                .read_text(
                    encoding="utf-8"
                )
                .splitlines()
            )
        except OSError:
            return {}

        for line in reversed(lines):
            if not line.strip():
                continue

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                return payload

        return {}

    @staticmethod
    def _get_first(
        payload: dict[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]

        return None

    def _extract_context(
        self,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        indoor_temperature = self._as_float(
            self._get_first(
                observation,
                "indoor_temperature_c",
                "indoor_temperature",
            )
        )

        outdoor_temperature = self._as_float(
            self._get_first(
                observation,
                "outdoor_temperature_c",
                "outdoor_temperature",
            )
        )

        floor_surface_temperature = (
            self._as_float(
                self._get_first(
                    observation,
                    "floor_surface_temperature_c",
                    "floor_surface_temperature",
                )
            )
        )

        floor_supply_temperature = (
            self._as_float(
                self._get_first(
                    observation,
                    "floor_supply_temperature_c",
                    "floor_supply_temperature",
                )
            )
        )

        floor_return_temperature = (
            self._as_float(
                self._get_first(
                    observation,
                    "floor_return_temperature_c",
                    "floor_return_temperature",
                )
            )
        )

        humidity = self._as_float(
            self._get_first(
                observation,
                "indoor_humidity_percent",
                "indoor_humidity",
            )
        )

        pump_running = self._as_bool(
            self._get_first(
                observation,
                "pump_running",
                "pump",
            )
        )

        valve_open = self._as_bool(
            self._get_first(
                observation,
                "valve_open",
                "valve",
            )
        )

        active_cooling = self._as_bool(
            self._get_first(
                observation,
                "active_cooling",
                "cooling_active",
            )
        )

        if (
            active_cooling is None
            and pump_running is not None
            and valve_open is not None
        ):
            active_cooling = bool(
                pump_running
                and valve_open
            )

        return {
            "timestamp": observation.get(
                "timestamp"
            ),
            "indoor_temperature_c": (
                indoor_temperature
            ),
            "outdoor_temperature_c": (
                outdoor_temperature
            ),
            "floor_surface_temperature_c": (
                floor_surface_temperature
            ),
            "floor_supply_temperature_c": (
                floor_supply_temperature
            ),
            "floor_return_temperature_c": (
                floor_return_temperature
            ),
            "indoor_humidity_percent": (
                humidity
            ),
            "pump_running": pump_running,
            "valve_open": valve_open,
            "active_cooling": active_cooling,
        }

    @staticmethod
    def _dew_point_c(
        temperature_c: float | None,
        humidity_percent: float | None,
    ) -> float | None:
        if (
            temperature_c is None
            or humidity_percent is None
            or humidity_percent <= 0
            or humidity_percent > 100
        ):
            return None

        a = 17.62
        b = 243.12

        gamma = (
            math.log(
                humidity_percent / 100.0
            )
            + (
                a * temperature_c
                / (
                    b + temperature_c
                )
            )
        )

        dew_point = (
            b * gamma
            / (
                a - gamma
            )
        )

        return round(
            dew_point,
            2,
        )

    def _condensation_analysis(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        dew_point = self._dew_point_c(
            context.get(
                "indoor_temperature_c"
            ),
            context.get(
                "indoor_humidity_percent"
            ),
        )

        reference_surface = (
            context.get(
                "floor_surface_temperature_c"
            )
        )

        if reference_surface is None:
            reference_surface = (
                context.get(
                    "floor_supply_temperature_c"
                )
            )

        if (
            dew_point is None
            or reference_surface is None
        ):
            return {
                "status": "UNKNOWN",
                "dew_point_c": dew_point,
                "reference_surface_temperature_c": (
                    reference_surface
                ),
                "margin_c": None,
                "minimum_margin_c": 3.0,
                "safe": None,
                "reason": (
                    "Mesures insuffisantes pour évaluer "
                    "le risque de condensation."
                ),
            }

        margin = (
            reference_surface
            - dew_point
        )

        safe = margin >= 3.0

        if margin < 1.0:
            status = "CRITICAL"

        elif margin < 3.0:
            status = "WARNING"

        else:
            status = "SAFE"

        return {
            "status": status,
            "dew_point_c": dew_point,
            "reference_surface_temperature_c": round(
                reference_surface,
                2,
            ),
            "margin_c": round(
                margin,
                2,
            ),
            "minimum_margin_c": 3.0,
            "safe": safe,
            "reason": (
                "Marge de condensation suffisante."
                if safe
                else (
                    "Marge de condensation insuffisante : "
                    "le refroidissement ne doit pas être recommandé."
                )
            ),
        }

    @staticmethod
    def _append_reason(
        reasons: list[dict[str, Any]],
        code: str,
        severity: str,
        message: str,
        value: Any = None,
    ) -> None:
        reasons.append(
            {
                "code": code,
                "severity": severity,
                "message": message,
                "value": value,
            }
        )

    def _persist(
        self,
        decision: dict[str, Any],
    ) -> None:
        temporary_path = (
            self.decision_path.with_suffix(
                ".json.tmp"
            )
        )

        temporary_path.write_text(
            json.dumps(
                decision,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            self.decision_path,
        )

        with self.history_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    decision,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

            handle.write("\n")
            handle.flush()
            os.fsync(
                handle.fileno()
            )

    def evaluate(
        self,
        target_temperature_c: float | None = None,
        horizon_minutes: int | None = None,
        persist: bool = True,
    ) -> dict[str, Any]:
        target = (
            float(
                target_temperature_c
            )
            if target_temperature_c is not None
            else self.comfort_target_c
        )

        horizon = (
            int(
                horizon_minutes
            )
            if horizon_minutes is not None
            else self.horizon_minutes
        )

        observation = (
            self._latest_observation()
        )

        context = self._extract_context(
            observation
        )

        indoor_temperature = (
            context.get(
                "indoor_temperature_c"
            )
        )

        generated_at = self._utc_now()

        reasons: list[
            dict[str, Any]
        ] = []

        if indoor_temperature is None:
            decision = {
                "version": self.VERSION,
                "status": "COLLECTING",
                "generated_at": generated_at,
                "advisory_action": "WAIT_FOR_DATA",
                "advisory_priority": "LOW",
                "summary": (
                    "Aucune recommandation thermique fiable : "
                    "la température intérieure est indisponible."
                ),
                "target_temperature_c": target,
                "confidence_percent": 0.0,
                "context": context,
                "prediction": None,
                "condensation": (
                    self._condensation_analysis(
                        context
                    )
                ),
                "reasons": [
                    {
                        "code": "NO_INDOOR_TEMPERATURE",
                        "severity": "BLOCKING",
                        "message": (
                            "Température intérieure absente."
                        ),
                        "value": None,
                    }
                ],
                "safety": self._safety_payload(),
            }

            if persist:
                self._persist(
                    decision
                )

            return decision

        try:
            comparison = (
                self.prediction_engine.compare(
                    target_temperature_c=target,
                    horizon_minutes=horizon,
                    step_minutes=30,
                )
            )

        except ValueError as exc:
            decision = {
                "version": self.VERSION,
                "status": "COLLECTING",
                "generated_at": generated_at,
                "advisory_action": "WAIT_FOR_DATA",
                "advisory_priority": "LOW",
                "summary": str(exc),
                "target_temperature_c": target,
                "confidence_percent": 0.0,
                "context": context,
                "prediction": None,
                "condensation": (
                    self._condensation_analysis(
                        context
                    )
                ),
                "reasons": [
                    {
                        "code": "PREDICTION_UNAVAILABLE",
                        "severity": "BLOCKING",
                        "message": str(exc),
                        "value": None,
                    }
                ],
                "safety": self._safety_payload(),
            }

            if persist:
                self._persist(
                    decision
                )

            return decision

        confidence = float(
            comparison.get(
                "global_confidence_percent",
                0.0,
            )
            or 0.0
        )

        cooling_benefit = float(
            comparison.get(
                "cooling_benefit_at_horizon_c",
                0.0,
            )
            or 0.0
        )

        cooling = comparison.get(
            "cooling",
            {},
        )

        passive = comparison.get(
            "passive",
            {},
        )

        minutes_to_target = (
            cooling.get(
                "minutes_to_target"
            )
        )

        predicted_cooling_temperature = (
            cooling.get(
                "predicted_temperature_at_horizon_c"
            )
        )

        predicted_passive_temperature = (
            passive.get(
                "predicted_temperature_at_horizon_c"
            )
        )

        condensation = (
            self._condensation_analysis(
                context
            )
        )

        active_cooling = bool(
            context.get(
                "active_cooling",
                False,
            )
        )

        action = "MAINTAIN_IDLE"
        priority = "LOW"
        status = "READY"

        if confidence < 20.0:
            status = "LIMITED"

        elif confidence < 60.0:
            status = "LEARNING"

        if condensation.get(
            "safe"
        ) is False:
            action = "STOP_OR_BLOCK_COOLING"
            priority = "CRITICAL"

            self._append_reason(
                reasons,
                "CONDENSATION_RISK",
                "BLOCKING",
                (
                    "La marge de condensation est "
                    "inférieure au minimum de sécurité."
                ),
                condensation.get(
                    "margin_c"
                ),
            )

        elif (
            indoor_temperature
            <= self.stop_threshold_c
        ):
            action = (
                "RECOMMEND_STOP_COOLING"
                if active_cooling
                else "MAINTAIN_IDLE"
            )

            priority = "NORMAL"

            self._append_reason(
                reasons,
                "COMFORT_REACHED",
                "INFO",
                (
                    "La température intérieure est au-dessous "
                    "du seuil d’arrêt."
                ),
                indoor_temperature,
            )

        elif (
            active_cooling
            and indoor_temperature
            > self.stop_threshold_c
        ):
            if (
                confidence
                < self.minimum_confidence_percent
            ):
                action = (
                    "CONTINUE_WITH_CAUTION"
                )
                priority = "NORMAL"

                self._append_reason(
                    reasons,
                    "LOW_CONFIDENCE_ACTIVE",
                    "WARNING",
                    (
                        "Le refroidissement est déjà actif, "
                        "mais la confiance du modèle reste faible."
                    ),
                    confidence,
                )

            elif cooling_benefit >= (
                self.minimum_benefit_c
            ):
                action = (
                    "RECOMMEND_CONTINUE_COOLING"
                )
                priority = "NORMAL"

                self._append_reason(
                    reasons,
                    "COOLING_EFFECTIVE",
                    "INFO",
                    (
                        "Le scénario refroidissement est plus "
                        "favorable que le scénario passif."
                    ),
                    cooling_benefit,
                )

            else:
                action = (
                    "REASSESS_COOLING"
                )
                priority = "NORMAL"

                self._append_reason(
                    reasons,
                    "LIMITED_COOLING_EFFECT",
                    "WARNING",
                    (
                        "Le bénéfice thermique prédit du "
                        "refroidissement est encore limité."
                    ),
                    cooling_benefit,
                )

        elif (
            indoor_temperature
            >= self.start_threshold_c
        ):
            if (
                confidence
                < self.minimum_confidence_percent
            ):
                action = (
                    "MONITOR_BEFORE_COOLING"
                )
                priority = "NORMAL"

                self._append_reason(
                    reasons,
                    "INSUFFICIENT_CONFIDENCE",
                    "WARNING",
                    (
                        "La température dépasse le seuil de départ, "
                        "mais la confiance du modèle reste insuffisante."
                    ),
                    confidence,
                )

            elif cooling_benefit >= (
                self.minimum_benefit_c
            ):
                action = (
                    "RECOMMEND_START_COOLING"
                )
                priority = "HIGH"

                self._append_reason(
                    reasons,
                    "START_THRESHOLD_REACHED",
                    "INFO",
                    (
                        "La température intérieure dépasse "
                        "le seuil de démarrage."
                    ),
                    indoor_temperature,
                )

                self._append_reason(
                    reasons,
                    "PREDICTED_COOLING_BENEFIT",
                    "INFO",
                    (
                        "Le refroidissement présente un bénéfice "
                        "thermique prévisible."
                    ),
                    cooling_benefit,
                )

            else:
                action = (
                    "MONITOR_THERMAL_EVOLUTION"
                )
                priority = "NORMAL"

                self._append_reason(
                    reasons,
                    "BENEFIT_TOO_LOW",
                    "WARNING",
                    (
                        "Le bénéfice prédit ne justifie pas encore "
                        "une recommandation de démarrage."
                    ),
                    cooling_benefit,
                )

        else:
            action = (
                "MAINTAIN_CURRENT_STATE"
            )
            priority = "LOW"

            self._append_reason(
                reasons,
                "TEMPERATURE_IN_HYSTERESIS",
                "INFO",
                (
                    "La température se situe dans la zone "
                    "d’hystérésis de confort."
                ),
                indoor_temperature,
            )

        if confidence < (
            self.minimum_confidence_percent
        ):
            self._append_reason(
                reasons,
                "MODEL_LEARNING",
                "WARNING",
                (
                    "Le modèle poursuit son apprentissage ; "
                    "la recommandation doit rester prudente."
                ),
                confidence,
            )

        if (
            cooling_benefit
            < self.minimum_benefit_c
        ):
            self._append_reason(
                reasons,
                "LOW_PREDICTED_DIFFERENCE",
                "INFO",
                (
                    "L’écart entre les scénarios passif et "
                    "refroidissement reste faible."
                ),
                cooling_benefit,
            )

        summary = self._build_summary(
            action=action,
            indoor_temperature=(
                indoor_temperature
            ),
            target_temperature=target,
            confidence=confidence,
            cooling_benefit=(
                cooling_benefit
            ),
            minutes_to_target=(
                minutes_to_target
            ),
        )

        decision = {
            "version": self.VERSION,
            "status": status,
            "generated_at": generated_at,
            "advisory_action": action,
            "advisory_priority": priority,
            "summary": summary,
            "target_temperature_c": round(
                target,
                2,
            ),
            "start_threshold_c": round(
                self.start_threshold_c,
                2,
            ),
            "stop_threshold_c": round(
                self.stop_threshold_c,
                2,
            ),
            "confidence_percent": round(
                confidence,
                1,
            ),
            "cooling_benefit_at_horizon_c": round(
                cooling_benefit,
                2,
            ),
            "minutes_to_target": (
                minutes_to_target
            ),
            "predicted_cooling_temperature_c": (
                predicted_cooling_temperature
            ),
            "predicted_passive_temperature_c": (
                predicted_passive_temperature
            ),
            "horizon_minutes": horizon,
            "context": context,
            "condensation": condensation,
            "prediction": {
                "status": comparison.get(
                    "status"
                ),
                "recommendation": comparison.get(
                    "advisory_recommendation"
                ),
                "cooling_rate_c_per_hour": (
                    cooling.get(
                        "cooling_rate_c_per_hour"
                    )
                ),
                "passive_rate_c_per_hour": (
                    passive.get(
                        "passive_rate_c_per_hour"
                    )
                ),
                "rate_sources": cooling.get(
                    "rate_sources"
                ),
                "observations_used": (
                    cooling.get(
                        "observations_used"
                    )
                ),
            },
            "reasons": reasons,
            "safety": self._safety_payload(),
        }

        if persist:
            self._persist(
                decision
            )

        return decision

    @staticmethod
    def _build_summary(
        action: str,
        indoor_temperature: float,
        target_temperature: float,
        confidence: float,
        cooling_benefit: float,
        minutes_to_target: int | None,
    ) -> str:
        action_labels = {
            "WAIT_FOR_DATA": (
                "attendre davantage de données"
            ),
            "STOP_OR_BLOCK_COOLING": (
                "bloquer ou arrêter le refroidissement"
            ),
            "RECOMMEND_STOP_COOLING": (
                "arrêter le refroidissement"
            ),
            "MAINTAIN_IDLE": (
                "maintenir le système au repos"
            ),
            "CONTINUE_WITH_CAUTION": (
                "poursuivre avec prudence"
            ),
            "RECOMMEND_CONTINUE_COOLING": (
                "poursuivre le refroidissement"
            ),
            "REASSESS_COOLING": (
                "réévaluer le refroidissement"
            ),
            "MONITOR_BEFORE_COOLING": (
                "surveiller avant démarrage"
            ),
            "RECOMMEND_START_COOLING": (
                "démarrer le refroidissement"
            ),
            "MONITOR_THERMAL_EVOLUTION": (
                "surveiller l’évolution thermique"
            ),
            "MAINTAIN_CURRENT_STATE": (
                "maintenir l’état actuel"
            ),
        }

        label = action_labels.get(
            action,
            action,
        )

        target_text = (
            f"{minutes_to_target} min"
            if minutes_to_target is not None
            else "non déterminé"
        )

        return (
            f"Recommandation : {label}. "
            f"Température intérieure {indoor_temperature:.2f} °C, "
            f"cible {target_temperature:.2f} °C, "
            f"confiance {confidence:.1f} %, "
            f"bénéfice prédit {cooling_benefit:.2f} °C, "
            f"délai estimé {target_text}."
        )

    @staticmethod
    def _safety_payload() -> dict[str, Any]:
        return {
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        }

    def latest(
        self,
    ) -> dict[str, Any]:
        if not self.decision_path.exists():
            return self.evaluate(
                persist=True
            )

        try:
            payload = json.loads(
                self.decision_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return self.evaluate(
                persist=True
            )

        if not isinstance(payload, dict):
            return self.evaluate(
                persist=True
            )

        return payload

    def history(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        limit = max(
            1,
            min(
                int(limit),
                500,
            ),
        )

        if not self.history_path.exists():
            return []

        try:
            lines = (
                self.history_path
                .read_text(
                    encoding="utf-8"
                )
                .splitlines()
            )
        except OSError:
            return []

        entries: list[
            dict[str, Any]
        ] = []

        for line in lines[-limit:]:
            if not line.strip():
                continue

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                entries.append(
                    payload
                )

        return entries

    def status(
        self,
    ) -> dict[str, Any]:
        prediction_status = (
            self.prediction_engine.status()
        )

        return {
            "version": self.VERSION,
            "status": prediction_status.get(
                "status",
                "COLLECTING",
            ),
            "decision_path": str(
                self.decision_path
            ),
            "decision_exists": (
                self.decision_path.exists()
            ),
            "history_path": str(
                self.history_path
            ),
            "history_exists": (
                self.history_path.exists()
            ),
            "comfort_target_c": round(
                self.comfort_target_c,
                2,
            ),
            "start_threshold_c": round(
                self.start_threshold_c,
                2,
            ),
            "stop_threshold_c": round(
                self.stop_threshold_c,
                2,
            ),
            "minimum_confidence_percent": round(
                self.minimum_confidence_percent,
                1,
            ),
            "minimum_benefit_c": round(
                self.minimum_benefit_c,
                2,
            ),
            "horizon_minutes": (
                self.horizon_minutes
            ),
            "observations_available": (
                prediction_status.get(
                    "observations_available",
                    0,
                )
            ),
            "prediction_confidence_percent": (
                prediction_status.get(
                    "global_confidence_percent",
                    0.0,
                )
            ),
            "data_directory_writable": (
                os.access(
                    self.data_directory,
                    os.W_OK,
                )
            ),
            **self._safety_payload(),
        }
