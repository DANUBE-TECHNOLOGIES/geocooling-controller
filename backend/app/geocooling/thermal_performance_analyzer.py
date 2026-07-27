"""
C015.2R1 — GeoCooling Thermal Performance Analyzer.

Analyse passive des performances thermiques.

Événement consommé :
    execution.analysis

Événements publiés :
    thermal.performance
    thermal.performance.warning

Aucune commande matérielle n'est exécutée.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class GeoCoolingThermalPerformanceAnalyzer:
    PATCH_VERSION = "C015.2R1"
    SUBSCRIPTION_ID = "c0152-thermal-performance-analyzer"

    TEMPERATURE_ALIASES = {
        "inlet": (
            "inlet_temperature_c",
            "water_in_temperature_c",
            "supply_temperature_c",
            "flow_temperature_c",
            "source_in_temperature_c",
            "temperature_in_c",
            "inlet_temp_c",
            "temp_in_c",
        ),
        "outlet": (
            "outlet_temperature_c",
            "water_out_temperature_c",
            "return_temperature_c",
            "source_out_temperature_c",
            "temperature_out_c",
            "outlet_temp_c",
            "temp_out_c",
        ),
        "indoor": (
            "indoor_temperature_c",
            "room_temperature_c",
            "inside_temperature_c",
            "ambient_temperature_c",
        ),
        "surface": (
            "surface_temperature_c",
            "floor_surface_temperature_c",
            "floor_temperature_c",
        ),
    }

    FLOW_ALIASES = (
        "flow_rate_l_min",
        "flow_l_min",
        "water_flow_l_min",
        "hydraulic_flow_l_min",
        "source_flow_l_min",
    )

    POWER_ALIASES = (
        "thermal_power_kw",
        "cooling_power_kw",
        "power_kw",
        "instantaneous_power_kw",
    )

    ENERGY_ALIASES = (
        "energy_transferred_kwh",
        "thermal_energy_kwh",
        "cooling_energy_kwh",
        "energy_kwh",
    )

    def __init__(
        self,
        *,
        controller: Any,
        thermal_engine: Any,
        subscription_manager: Any,
        event_bus: Any,
        history_capacity: int = 500,
        event_capacity: int = 1000,
    ) -> None:
        self.controller = controller
        self.thermal_engine = thermal_engine
        self.subscription_manager = subscription_manager
        self.event_bus = event_bus

        self.history_capacity = max(
            50,
            int(history_capacity),
        )
        self.event_capacity = max(
            100,
            int(event_capacity),
        )

        self._lock = threading.RLock()
        self._started_at = self._utc_now()

        self._analyses: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )
        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.event_capacity
        )

        self._metrics = {
            "received_count": 0,
            "analysis_count": 0,
            "available_analysis_count": 0,
            "unavailable_analysis_count": 0,
            "warning_count": 0,
            "anomaly_count": 0,
            "publish_error_count": 0,
            "last_analysis_at": None,
            "last_session_id": None,
            "last_score": None,
            "last_classification": None,
            "last_error": None,
        }

        self.subscription_id = (
            self.subscription_manager.subscribe(
                "execution.analysis",
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
            return event.get("payload", event)

        payload = getattr(event, "payload", None)

        if payload is not None:
            return payload

        return event

    @classmethod
    def _walk(
        cls,
        value: Any,
    ):
        if isinstance(value, dict):
            for key, item in value.items():
                yield str(key), item
                yield from cls._walk(item)

        elif isinstance(value, (list, tuple)):
            for item in value:
                yield from cls._walk(item)

        elif hasattr(value, "__dict__"):
            yield from cls._walk(vars(value))

    @classmethod
    def _number(
        cls,
        value: Any,
    ) -> float | None:
        if isinstance(value, bool) or value is None:
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(number) or math.isinf(number):
            return None

        return number

    @classmethod
    def _find_number(
        cls,
        sources: list[Any],
        aliases: tuple[str, ...],
    ) -> float | None:
        normalized_aliases = {
            alias.lower()
            for alias in aliases
        }

        for source in sources:
            for key, value in cls._walk(source):
                if key.lower() in normalized_aliases:
                    number = cls._number(value)

                    if number is not None:
                        return number

        return None

    def _thermal_sources(
        self,
    ) -> dict[str, Any]:
        metrics: dict[str, Any]

        try:
            raw_metrics = self.thermal_engine.metrics()
            metrics = (
                raw_metrics
                if isinstance(raw_metrics, dict)
                else {}
            )
        except Exception as exc:
            metrics = {
                "available": False,
                "reason": repr(exc),
            }

        try:
            latest_raw = self.thermal_engine.latest()
            latest = self._safe(latest_raw)
        except Exception as exc:
            latest = {
                "error": repr(exc),
            }

        try:
            history_raw = self.thermal_engine.history(200)
            history = (
                history_raw
                if isinstance(history_raw, list)
                else []
            )
        except Exception as exc:
            history = [
                {
                    "error": repr(exc),
                }
            ]

        try:
            controller_status = self.controller.status()

            if not isinstance(controller_status, dict):
                controller_status = {}
        except Exception as exc:
            controller_status = {
                "error": repr(exc),
            }

        return {
            "metrics": self._safe(metrics),
            "latest": self._safe(latest),
            "history": self._safe(history),
            "controller": self._safe(
                controller_status
            ),
        }

    @staticmethod
    def _round(
        value: float | None,
        digits: int = 3,
    ) -> float | None:
        if value is None:
            return None

        return round(value, digits)

    def analyze(
        self,
        *,
        execution_analysis: dict[str, Any] | None = None,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        generated_at = self._utc_now()
        sources = self._thermal_sources()

        execution = (
            execution_analysis
            if isinstance(execution_analysis, dict)
            else {}
        )

        searchable = [
            sources["metrics"],
            sources["latest"],
            sources["history"],
            sources["controller"],
            execution,
        ]

        inlet = self._find_number(
            searchable,
            self.TEMPERATURE_ALIASES["inlet"],
        )
        outlet = self._find_number(
            searchable,
            self.TEMPERATURE_ALIASES["outlet"],
        )
        indoor = self._find_number(
            searchable,
            self.TEMPERATURE_ALIASES["indoor"],
        )
        surface = self._find_number(
            searchable,
            self.TEMPERATURE_ALIASES["surface"],
        )
        flow = self._find_number(
            searchable,
            self.FLOW_ALIASES,
        )
        reported_power = self._find_number(
            searchable,
            self.POWER_ALIASES,
        )
        energy = self._find_number(
            searchable,
            self.ENERGY_ALIASES,
        )

        delta_t = None

        if inlet is not None and outlet is not None:
            delta_t = abs(
                inlet - outlet
            )

        calculated_power = None

        if flow is not None and delta_t is not None:
            # Eau : P(kW) ≈ 0,06977 × débit(l/min) × ΔT(K)
            calculated_power = (
                0.06977
                * flow
                * delta_t
            )

        effective_power = (
            reported_power
            if reported_power is not None
            else calculated_power
        )

        warnings: list[dict[str, Any]] = []
        anomalies: list[dict[str, Any]] = []
        recommendations: list[str] = []

        score = 100

        thermal_available = bool(
            sources["metrics"].get(
                "available",
                False,
            )
        )

        if not thermal_available:
            score -= 50

            warnings.append(
                {
                    "type": "thermal_data_unavailable",
                    "reason": sources["metrics"].get(
                        "reason",
                        "Aucune mesure thermique exploitable.",
                    ),
                }
            )

        if inlet is None:
            score -= 10
            warnings.append(
                {
                    "type": "inlet_temperature_missing",
                }
            )

        if outlet is None:
            score -= 10
            warnings.append(
                {
                    "type": "outlet_temperature_missing",
                }
            )

        if flow is None:
            score -= 10
            warnings.append(
                {
                    "type": "flow_rate_missing",
                }
            )

        if delta_t is not None:
            if delta_t < 0.2:
                score -= 25
                anomalies.append(
                    {
                        "type": "delta_t_too_low",
                        "delta_t_c": self._round(
                            delta_t
                        ),
                    }
                )

            elif delta_t > 15:
                score -= 20
                anomalies.append(
                    {
                        "type": "delta_t_implausibly_high",
                        "delta_t_c": self._round(
                            delta_t
                        ),
                    }
                )

        if flow is not None and flow <= 0:
            score -= 35
            anomalies.append(
                {
                    "type": "zero_or_negative_flow",
                    "flow_rate_l_min": flow,
                }
            )

        if effective_power is not None:
            if effective_power < 0:
                score -= 30
                anomalies.append(
                    {
                        "type": "negative_thermal_power",
                        "thermal_power_kw":
                            self._round(
                                effective_power
                            ),
                    }
                )

            elif effective_power < 0.2:
                score -= 10
                warnings.append(
                    {
                        "type": "low_thermal_power",
                        "thermal_power_kw":
                            self._round(
                                effective_power
                            ),
                    }
                )

        execution_score = self._number(
            execution.get("quality_score")
        )

        if execution_score is not None:
            combined_score = round(
                (
                    max(0, min(100, score))
                    + max(
                        0,
                        min(
                            100,
                            execution_score,
                        ),
                    )
                )
                / 2
            )
        else:
            combined_score = round(
                max(
                    0,
                    min(100, score),
                )
            )

        if not thermal_available:
            classification = "UNAVAILABLE"

        elif anomalies:
            classification = "ANOMALOUS"

        elif combined_score >= 90:
            classification = "EXCELLENT"

        elif combined_score >= 80:
            classification = "GOOD"

        elif combined_score >= 65:
            classification = "ACCEPTABLE"

        else:
            classification = "LIMITED"

        if flow is None:
            recommendations.append(
                "Configurer ou mesurer le débit hydraulique "
                "pour calculer la puissance thermique."
            )

        if inlet is None or outlet is None:
            recommendations.append(
                "Valider l'affectation des sondes entrée et "
                "sortie du circuit géocooling."
            )

        if not thermal_available:
            recommendations.append(
                "Injecter les mesures DS18B20 dans "
                "ThermalEngine.ingest()."
            )

        if anomalies:
            recommendations.append(
                "Contrôler les sondes, le débit et le sens "
                "hydraulique avant le pilotage automatique."
            )

        if not recommendations:
            recommendations.append(
                "Performance thermique cohérente."
            )

        session_id = execution.get(
            "session_id"
        )

        result = {
            "analysis_id": (
                f"{session_id or 'manual'}:"
                f"{generated_at}"
            ),
            "generated_at": generated_at,
            "trigger": trigger,
            "session_id": session_id,
            "available": thermal_available,
            "classification": classification,
            "thermal_score": combined_score,
            "execution_quality_score":
                execution_score,
            "measurements": {
                "inlet_temperature_c":
                    self._round(inlet),
                "outlet_temperature_c":
                    self._round(outlet),
                "indoor_temperature_c":
                    self._round(indoor),
                "surface_temperature_c":
                    self._round(surface),
                "flow_rate_l_min":
                    self._round(flow),
                "delta_t_c":
                    self._round(delta_t),
                "reported_thermal_power_kw":
                    self._round(
                        reported_power
                    ),
                "calculated_thermal_power_kw":
                    self._round(
                        calculated_power
                    ),
                "effective_thermal_power_kw":
                    self._round(
                        effective_power
                    ),
                "energy_transferred_kwh":
                    self._round(
                        energy
                    ),
            },
            "warning_count": len(warnings),
            "anomaly_count": len(anomalies),
            "warnings": warnings,
            "anomalies": anomalies,
            "recommendations": recommendations,
            "thermal_engine": {
                "metrics": sources["metrics"],
                "latest": sources["latest"],
                "history_count": len(
                    sources["history"]
                ),
            },
            "execution_analysis": self._safe(
                execution
            ),
        }

        with self._lock:
            self._analyses.append(
                deepcopy(result)
            )

            self._metrics[
                "analysis_count"
            ] += 1

            if thermal_available:
                self._metrics[
                    "available_analysis_count"
                ] += 1
            else:
                self._metrics[
                    "unavailable_analysis_count"
                ] += 1

            self._metrics[
                "warning_count"
            ] += len(warnings)

            self._metrics[
                "anomaly_count"
            ] += len(anomalies)

            self._metrics[
                "last_analysis_at"
            ] = generated_at

            self._metrics[
                "last_session_id"
            ] = session_id

            self._metrics[
                "last_score"
            ] = combined_score

            self._metrics[
                "last_classification"
            ] = classification

            self._events.append(
                {
                    "timestamp": generated_at,
                    "trigger": trigger,
                    "session_id": session_id,
                    "classification":
                        classification,
                    "thermal_score":
                        combined_score,
                }
            )

        level = "INFO"

        if classification in {
            "LIMITED",
            "UNAVAILABLE",
        }:
            level = "WARN"

        if classification == "ANOMALOUS":
            level = "ERROR"

        self._publish(
            "thermal.performance",
            result,
            level,
        )

        if warnings or anomalies:
            self._publish(
                "thermal.performance.warning",
                {
                    "session_id": session_id,
                    "classification":
                        classification,
                    "thermal_score":
                        combined_score,
                    "warnings": warnings,
                    "anomalies": anomalies,
                },
                (
                    "ERROR"
                    if anomalies
                    else "WARN"
                ),
            )

        return deepcopy(result)

    def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        level: str,
    ) -> None:
        try:
            self.event_bus.publish(
                event_type=event_type,
                source=(
                    "thermal-performance-analyzer"
                ),
                payload=self._safe(payload),
                level=level,
            )

            self._metrics["last_error"] = None

        except Exception as exc:
            with self._lock:
                self._metrics[
                    "publish_error_count"
                ] += 1
                self._metrics[
                    "last_error"
                ] = repr(exc)

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

        execution = (
            payload
            if isinstance(payload, dict)
            else {}
        )

        self.analyze(
            execution_analysis=execution,
            trigger=event_type,
        )

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "overall": "OK",
                "component":
                    "thermal_performance_analyzer",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "started_at": self._started_at,
                "subscription_id":
                    self.subscription_id,
                "consumes": [
                    "execution.analysis"
                ],
                "publishes": [
                    "thermal.performance",
                    "thermal.performance.warning",
                ],
                "history_count":
                    len(self._analyses),
                "event_count":
                    len(self._events),
                "metrics":
                    deepcopy(self._metrics),
            }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            analysis = (
                deepcopy(self._analyses[-1])
                if self._analyses
                else None
            )

        return {
            "overall": "OK",
            "component":
                "thermal_performance_analyzer",
            "available": analysis is not None,
            "analysis": analysis,
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
                self._analyses
            )[-limit:]

        return {
            "overall": "OK",
            "component":
                "thermal_performance_analyzer",
            "limit": limit,
            "count": len(items),
            "analyses": deepcopy(items),
        }

    def event_history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                self.event_capacity,
            ),
        )

        with self._lock:
            items = list(
                self._events
            )[-limit:]

        return {
            "overall": "OK",
            "component":
                "thermal_performance_analyzer",
            "limit": limit,
            "count": len(items),
            "events": deepcopy(items),
        }
