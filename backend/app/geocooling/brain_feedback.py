"""
C015.3R1 — Brain Feedback & Adaptive Memory.

Le composant apprend passivement des performances observées.

Événement consommé :
    thermal.performance

Événements publiés :
    brain.feedback
    brain.feedback.warning

Important :
    - aucune commande matérielle ;
    - aucun changement automatique de configuration ;
    - aucune modification automatique des seuils du Brain ;
    - recommandations uniquement.
"""

from __future__ import annotations

import json
import math
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from statistics import mean, median
from typing import Any

from sqlalchemy import text


class GeoCoolingBrainFeedback:
    PATCH_VERSION = "C015.3R1"
    SUBSCRIPTION_ID = "c0153-brain-feedback"

    VALID_CLASSIFICATIONS = {
        "EXCELLENT",
        "GOOD",
        "ACCEPTABLE",
        "LIMITED",
        "ANOMALOUS",
        "UNAVAILABLE",
    }

    def __init__(
        self,
        *,
        controller: Any,
        subscription_manager: Any,
        event_bus: Any,
        engine: Any,
        history_capacity: int = 1000,
        rolling_window: int = 20,
    ) -> None:
        self.controller = controller
        self.subscription_manager = subscription_manager
        self.event_bus = event_bus
        self.engine = engine

        self.history_capacity = max(
            100,
            int(history_capacity),
        )

        self.rolling_window = max(
            3,
            min(
                int(rolling_window),
                100,
            ),
        )

        self._lock = threading.RLock()
        self._started_at = self._utc_now()

        self._feedback_history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._thermal_scores: deque[float] = deque(
            maxlen=self.rolling_window
        )

        self._execution_scores: deque[float] = deque(
            maxlen=self.rolling_window
        )

        self._power_values: deque[float] = deque(
            maxlen=self.rolling_window
        )

        self._delta_t_values: deque[float] = deque(
            maxlen=self.rolling_window
        )

        self._energy_values: deque[float] = deque(
            maxlen=self.rolling_window
        )

        self._metrics: dict[str, Any] = {
            "received_count": 0,
            "accepted_count": 0,
            "ignored_count": 0,
            "feedback_count": 0,
            "positive_feedback_count": 0,
            "neutral_feedback_count": 0,
            "negative_feedback_count": 0,
            "unavailable_feedback_count": 0,
            "warning_count": 0,
            "database_write_count": 0,
            "database_error_count": 0,
            "publish_error_count": 0,
            "last_feedback_at": None,
            "last_session_id": None,
            "last_feedback_type": None,
            "last_learning_confidence": None,
            "last_runtime_factor": None,
            "last_error": None,
        }

        self._initialize_database()
        self._load_recent_memory()

        self.subscription_id = (
            self.subscription_manager.subscribe(
                "thermal.performance",
                self._consume,
                subscription_id=self.SUBSCRIPTION_ID,
            )
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @classmethod
    def _safe(cls, value: Any) -> Any:
        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    return None

            return value

        if isinstance(value, dict):
            return {
                str(key): cls._safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                cls._safe(item)
                for item in value
            ]

        if hasattr(value, "__dict__"):
            return cls._safe(vars(value))

        value_attribute = getattr(
            value,
            "value",
            None,
        )

        if isinstance(
            value_attribute,
            (bool, int, float, str),
        ):
            return cls._safe(value_attribute)

        isoformat = getattr(
            value,
            "isoformat",
            None,
        )

        if callable(isoformat):
            try:
                return isoformat()
            except Exception:
                pass

        return repr(value)

    @staticmethod
    def _payload(event: Any) -> Any:
        if isinstance(event, dict):
            return event.get(
                "payload",
                event,
            )

        payload = getattr(
            event,
            "payload",
            None,
        )

        if payload is not None:
            return payload

        return event

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(result) or math.isinf(result):
            return None

        return result

    @staticmethod
    def _bounded(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(
            minimum,
            min(
                maximum,
                value,
            ),
        )

    @staticmethod
    def _round(
        value: float | None,
        digits: int = 3,
    ) -> float | None:
        if value is None:
            return None

        return round(
            value,
            digits,
        )

    def _initialize_database(self) -> None:
        statement = text(
            """
            CREATE TABLE IF NOT EXISTS
            geocooling_brain_feedback (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ
                    NOT NULL DEFAULT NOW(),
                session_id TEXT,
                feedback_type TEXT NOT NULL,
                classification TEXT,
                thermal_score DOUBLE PRECISION,
                execution_score DOUBLE PRECISION,
                learning_confidence DOUBLE PRECISION,
                runtime_factor DOUBLE PRECISION,
                payload JSONB NOT NULL
            )
            """
        )

        index_statement = text(
            """
            CREATE INDEX IF NOT EXISTS
            idx_geocooling_brain_feedback_created_at
            ON geocooling_brain_feedback (
                created_at DESC
            )
            """
        )

        try:
            with self.engine.begin() as connection:
                connection.execute(statement)
                connection.execute(index_statement)

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "database_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def _load_recent_memory(self) -> None:
        statement = text(
            """
            SELECT payload
            FROM geocooling_brain_feedback
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )

        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    statement,
                    {
                        "limit": self.rolling_window,
                    },
                ).fetchall()

            for row in reversed(rows):
                payload = row[0]

                if isinstance(payload, str):
                    payload = json.loads(payload)

                if not isinstance(payload, dict):
                    continue

                self._restore_sample(payload)

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "database_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def _restore_sample(
        self,
        feedback: dict[str, Any],
    ) -> None:
        thermal_score = self._number(
            feedback.get("thermal_score")
        )

        execution_score = self._number(
            feedback.get(
                "execution_quality_score"
            )
        )

        measurements = feedback.get(
            "measurements"
        )

        if not isinstance(measurements, dict):
            measurements = {}

        power = self._number(
            measurements.get(
                "effective_thermal_power_kw"
            )
        )

        delta_t = self._number(
            measurements.get("delta_t_c")
        )

        energy = self._number(
            measurements.get(
                "energy_transferred_kwh"
            )
        )

        if thermal_score is not None:
            self._thermal_scores.append(
                thermal_score
            )

        if execution_score is not None:
            self._execution_scores.append(
                execution_score
            )

        if power is not None:
            self._power_values.append(power)

        if delta_t is not None:
            self._delta_t_values.append(
                delta_t
            )

        if energy is not None:
            self._energy_values.append(
                energy
            )

    def _rolling_statistics(
        self,
    ) -> dict[str, Any]:
        def stats(
            values: deque[float],
        ) -> dict[str, Any]:
            items = list(values)

            if not items:
                return {
                    "count": 0,
                    "average": None,
                    "median": None,
                    "minimum": None,
                    "maximum": None,
                }

            return {
                "count": len(items),
                "average": self._round(
                    mean(items)
                ),
                "median": self._round(
                    median(items)
                ),
                "minimum": self._round(
                    min(items)
                ),
                "maximum": self._round(
                    max(items)
                ),
            }

        return {
            "window_size": self.rolling_window,
            "thermal_score":
                stats(self._thermal_scores),
            "execution_score":
                stats(self._execution_scores),
            "thermal_power_kw":
                stats(self._power_values),
            "delta_t_c":
                stats(self._delta_t_values),
            "energy_kwh":
                stats(self._energy_values),
        }

    def _derive_feedback(
        self,
        thermal_performance: dict[str, Any],
    ) -> dict[str, Any]:
        generated_at = self._utc_now()

        classification = str(
            thermal_performance.get(
                "classification",
                "UNAVAILABLE",
            )
        ).strip().upper()

        if classification not in self.VALID_CLASSIFICATIONS:
            classification = "UNAVAILABLE"

        session_id = thermal_performance.get(
            "session_id"
        )

        thermal_score = self._number(
            thermal_performance.get(
                "thermal_score"
            )
        )

        execution_score = self._number(
            thermal_performance.get(
                "execution_quality_score"
            )
        )

        measurements = thermal_performance.get(
            "measurements"
        )

        if not isinstance(measurements, dict):
            measurements = {}

        delta_t = self._number(
            measurements.get("delta_t_c")
        )

        power = self._number(
            measurements.get(
                "effective_thermal_power_kw"
            )
        )

        energy = self._number(
            measurements.get(
                "energy_transferred_kwh"
            )
        )

        available = bool(
            thermal_performance.get(
                "available",
                False,
            )
        )

        warnings = thermal_performance.get(
            "warnings"
        )

        if not isinstance(warnings, list):
            warnings = []

        anomalies = thermal_performance.get(
            "anomalies"
        )

        if not isinstance(anomalies, list):
            anomalies = []

        baseline_before = self._rolling_statistics()

        previous_average = self._number(
            baseline_before[
                "thermal_score"
            ].get("average")
        )

        score_delta = None

        if (
            thermal_score is not None
            and previous_average is not None
        ):
            score_delta = (
                thermal_score
                - previous_average
            )

        if not available or classification == "UNAVAILABLE":
            feedback_type = "UNAVAILABLE"

        elif classification in {
            "EXCELLENT",
            "GOOD",
        } and not anomalies:
            feedback_type = "POSITIVE"

        elif classification in {
            "ANOMALOUS",
            "LIMITED",
        } or anomalies:
            feedback_type = "NEGATIVE"

        else:
            feedback_type = "NEUTRAL"

        sample_count = (
            baseline_before[
                "thermal_score"
            ]["count"]
        )

        data_completeness = 0.0

        for value in (
            thermal_score,
            execution_score,
            delta_t,
            power,
        ):
            if value is not None:
                data_completeness += 0.25

        learning_confidence = (
            min(
                1.0,
                sample_count
                / float(self.rolling_window),
            )
            * 0.6
            + data_completeness * 0.4
        )

        learning_confidence = self._bounded(
            learning_confidence,
            0.0,
            1.0,
        )

        runtime_factor = 1.0

        if feedback_type == "POSITIVE":
            if (
                thermal_score is not None
                and thermal_score >= 92
            ):
                runtime_factor = 0.95
            else:
                runtime_factor = 1.0

        elif feedback_type == "NEGATIVE":
            anomaly_types = {
                str(item.get("type"))
                for item in anomalies
                if isinstance(item, dict)
            }

            if {
                "zero_or_negative_flow",
                "thermal_safety_unsafe",
                "negative_thermal_power",
            } & anomaly_types:
                runtime_factor = 0.75

            elif (
                thermal_score is not None
                and thermal_score < 50
            ):
                runtime_factor = 0.85

            else:
                runtime_factor = 0.9

        elif feedback_type == "UNAVAILABLE":
            runtime_factor = 1.0

        runtime_factor = self._bounded(
            runtime_factor,
            0.75,
            1.10,
        )

        recommendations: list[str] = []

        if feedback_type == "POSITIVE":
            recommendations.append(
                "Conserver les paramètres actuels : "
                "le cycle présente une bonne performance."
            )

            if runtime_factor < 1.0:
                recommendations.append(
                    "Une réduction prudente de la durée "
                    "pourrait être testée en simulation."
                )

        elif feedback_type == "NEGATIVE":
            recommendations.append(
                "Ne pas augmenter automatiquement la durée "
                "avant d'avoir identifié la cause de la "
                "contre-performance."
            )

            if anomalies:
                recommendations.append(
                    "Traiter les anomalies thermiques ou "
                    "hydrauliques avant tout apprentissage."
                )

        elif feedback_type == "UNAVAILABLE":
            recommendations.append(
                "Apprentissage suspendu tant que les mesures "
                "thermiques ne sont pas disponibles."
            )

        else:
            recommendations.append(
                "Accumuler davantage de cycles avant "
                "d'adapter les paramètres."
            )

        if learning_confidence < 0.5:
            recommendations.append(
                "Confiance insuffisante : recommandation "
                "informative uniquement."
            )

        advisory_allowed = bool(
            available
            and feedback_type
            in {
                "POSITIVE",
                "NEUTRAL",
            }
            and learning_confidence >= 0.5
            and not anomalies
        )

        feedback = {
            "feedback_id": (
                f"{session_id or 'unknown'}:"
                f"{generated_at}"
            ),
            "generated_at": generated_at,
            "session_id": session_id,
            "feedback_type": feedback_type,
            "classification": classification,
            "thermal_score": (
                self._round(thermal_score)
            ),
            "execution_quality_score": (
                self._round(execution_score)
            ),
            "score_delta_from_baseline": (
                self._round(score_delta)
            ),
            "learning_confidence": (
                self._round(
                    learning_confidence,
                    4,
                )
            ),
            "suggested_runtime_factor": (
                self._round(
                    runtime_factor,
                    3,
                )
            ),
            "advisory_allowed":
                advisory_allowed,
            "automatic_application": False,
            "measurements": {
                "delta_t_c":
                    self._round(delta_t),
                "effective_thermal_power_kw":
                    self._round(power),
                "energy_transferred_kwh":
                    self._round(energy),
            },
            "warning_count": len(warnings),
            "anomaly_count": len(anomalies),
            "warnings": self._safe(warnings),
            "anomalies":
                self._safe(anomalies),
            "recommendations":
                recommendations,
            "baseline_before":
                baseline_before,
            "source":
                self._safe(
                    thermal_performance
                ),
        }

        return feedback

    def _persist(
        self,
        feedback: dict[str, Any],
    ) -> None:
        statement = text(
            """
            INSERT INTO geocooling_brain_feedback (
                session_id,
                feedback_type,
                classification,
                thermal_score,
                execution_score,
                learning_confidence,
                runtime_factor,
                payload
            )
            VALUES (
                :session_id,
                :feedback_type,
                :classification,
                :thermal_score,
                :execution_score,
                :learning_confidence,
                :runtime_factor,
                CAST(:payload AS JSONB)
            )
            """
        )

        try:
            with self.engine.begin() as connection:
                connection.execute(
                    statement,
                    {
                        "session_id":
                            feedback.get(
                                "session_id"
                            ),
                        "feedback_type":
                            feedback[
                                "feedback_type"
                            ],
                        "classification":
                            feedback.get(
                                "classification"
                            ),
                        "thermal_score":
                            feedback.get(
                                "thermal_score"
                            ),
                        "execution_score":
                            feedback.get(
                                "execution_quality_score"
                            ),
                        "learning_confidence":
                            feedback.get(
                                "learning_confidence"
                            ),
                        "runtime_factor":
                            feedback.get(
                                "suggested_runtime_factor"
                            ),
                        "payload": json.dumps(
                            self._safe(feedback),
                            ensure_ascii=False,
                        ),
                    },
                )

            self._metrics[
                "database_write_count"
            ] += 1

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "database_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def _publish(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        level: str,
    ) -> None:
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="brain-feedback",
                payload=self._safe(payload),
                level=level,
            )

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "publish_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def process(
        self,
        thermal_performance: dict[str, Any],
        *,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        if not isinstance(
            thermal_performance,
            dict,
        ):
            raise TypeError(
                "thermal_performance doit être "
                "un dictionnaire."
            )

        feedback = self._derive_feedback(
            thermal_performance
        )

        feedback["trigger"] = trigger

        with self._lock:
            self._restore_sample(feedback)

            feedback[
                "baseline_after"
            ] = self._rolling_statistics()

            self._feedback_history.append(
                deepcopy(feedback)
            )

            self._metrics[
                "accepted_count"
            ] += 1

            self._metrics[
                "feedback_count"
            ] += 1

            feedback_type = feedback[
                "feedback_type"
            ]

            if feedback_type == "POSITIVE":
                self._metrics[
                    "positive_feedback_count"
                ] += 1

            elif feedback_type == "NEGATIVE":
                self._metrics[
                    "negative_feedback_count"
                ] += 1

            elif feedback_type == "UNAVAILABLE":
                self._metrics[
                    "unavailable_feedback_count"
                ] += 1

            else:
                self._metrics[
                    "neutral_feedback_count"
                ] += 1

            if (
                feedback["warning_count"] > 0
                or feedback[
                    "anomaly_count"
                ] > 0
            ):
                self._metrics[
                    "warning_count"
                ] += 1

            self._metrics[
                "last_feedback_at"
            ] = feedback["generated_at"]

            self._metrics[
                "last_session_id"
            ] = feedback.get(
                "session_id"
            )

            self._metrics[
                "last_feedback_type"
            ] = feedback_type

            self._metrics[
                "last_learning_confidence"
            ] = feedback[
                "learning_confidence"
            ]

            self._metrics[
                "last_runtime_factor"
            ] = feedback[
                "suggested_runtime_factor"
            ]

        self._persist(feedback)

        level = "INFO"

        if feedback["feedback_type"] in {
            "NEGATIVE",
            "UNAVAILABLE",
        }:
            level = "WARN"

        if feedback["anomaly_count"] > 0:
            level = "ERROR"

        self._publish(
            event_type="brain.feedback",
            payload=feedback,
            level=level,
        )

        if (
            feedback["warning_count"] > 0
            or feedback["anomaly_count"] > 0
        ):
            self._publish(
                event_type="brain.feedback.warning",
                payload={
                    "session_id":
                        feedback.get(
                            "session_id"
                        ),
                    "feedback_type":
                        feedback[
                            "feedback_type"
                        ],
                    "learning_confidence":
                        feedback[
                            "learning_confidence"
                        ],
                    "suggested_runtime_factor":
                        feedback[
                            "suggested_runtime_factor"
                        ],
                    "warnings":
                        feedback["warnings"],
                    "anomalies":
                        feedback["anomalies"],
                },
                level=(
                    "ERROR"
                    if feedback[
                        "anomaly_count"
                    ] > 0
                    else "WARN"
                ),
            )

        return deepcopy(feedback)

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        payload = self._payload(event)

        with self._lock:
            self._metrics[
                "received_count"
            ] += 1

        if not isinstance(payload, dict):
            with self._lock:
                self._metrics[
                    "ignored_count"
                ] += 1

            return

        self.process(
            payload,
            trigger=event_type,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "overall": "OK",
                "component":
                    "brain_feedback",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "started_at":
                    self._started_at,
                "subscription_id":
                    self.subscription_id,
                "consumes": [
                    "thermal.performance"
                ],
                "publishes": [
                    "brain.feedback",
                    "brain.feedback.warning",
                ],
                "automatic_application":
                    False,
                "rolling_window":
                    self.rolling_window,
                "history_count":
                    len(
                        self._feedback_history
                    ),
                "memory":
                    self._rolling_statistics(),
                "metrics":
                    deepcopy(
                        self._metrics
                    ),
            }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            feedback = (
                deepcopy(
                    self._feedback_history[-1]
                )
                if self._feedback_history
                else None
            )

        return {
            "overall": "OK",
            "component":
                "brain_feedback",
            "available":
                feedback is not None,
            "feedback": feedback,
        }

    def history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                self.history_capacity,
            ),
        )

        with self._lock:
            items = list(
                self._feedback_history
            )[-limit:]

        return {
            "overall": "OK",
            "component":
                "brain_feedback",
            "limit": limit,
            "count": len(items),
            "feedback": deepcopy(items),
        }

    def database_history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                1000,
            ),
        )

        statement = text(
            """
            SELECT
                id,
                created_at,
                session_id,
                feedback_type,
                classification,
                thermal_score,
                execution_score,
                learning_confidence,
                runtime_factor,
                payload
            FROM geocooling_brain_feedback
            ORDER BY created_at DESC
            LIMIT :limit
            """
        )

        try:
            with self.engine.connect() as connection:
                rows = connection.execute(
                    statement,
                    {
                        "limit": limit,
                    },
                ).mappings().all()

            items = [
                self._safe(dict(row))
                for row in rows
            ]

            return {
                "overall": "OK",
                "component":
                    "brain_feedback",
                "persistent": True,
                "limit": limit,
                "count": len(items),
                "feedback": items,
            }

        except Exception as exc:
            return {
                "overall": "ERROR",
                "component":
                    "brain_feedback",
                "persistent": True,
                "limit": limit,
                "count": 0,
                "feedback": [],
                "error": repr(exc),
            }
