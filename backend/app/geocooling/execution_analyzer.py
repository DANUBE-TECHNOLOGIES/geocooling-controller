"""
C015.1R1 — GeoCooling Execution Analyzer.

Analyse passive des événements produits par
GeoCoolingExecutionSupervisor.

Le composant ne commande aucun actionneur.

Événements consommés :
    execution.started
    execution.running
    execution.stopping
    execution.completed
    execution.failed
    execution.reset

Événements publiés :
    execution.analysis
    execution.analysis.warning
"""

from __future__ import annotations

import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class GeoCoolingExecutionAnalyzer:
    """Analyse la cohérence et la qualité des cycles d'exécution."""

    PATCH_VERSION = "C015.1R1"

    OBSERVED_EVENT_TYPES = (
        "execution.started",
        "execution.running",
        "execution.stopping",
        "execution.completed",
        "execution.failed",
        "execution.reset",
    )

    TERMINAL_EVENT_TYPES = {
        "execution.completed",
        "execution.failed",
        "execution.reset",
    }

    EXPECTED_TRANSITIONS = {
        None: {
            "execution.started",
            "execution.failed",
            "execution.completed",
            "execution.reset",
        },
        "execution.started": {
            "execution.running",
            "execution.failed",
            "execution.reset",
        },
        "execution.running": {
            "execution.stopping",
            "execution.failed",
            "execution.reset",
        },
        "execution.stopping": {
            "execution.completed",
            "execution.failed",
            "execution.reset",
        },
    }

    def __init__(
        self,
        *,
        controller: Any,
        subscription_manager: Any,
        event_bus: Any,
        history_capacity: int = 500,
        event_capacity: int = 2000,
    ) -> None:
        self.controller = controller
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

        self._cycles: dict[str, dict[str, Any]] = {}

        self._analyses: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.event_capacity
        )

        self._subscriptions: list[str] = []

        self._metrics: dict[str, Any] = {
            "received_count": 0,
            "processed_count": 0,
            "ignored_count": 0,
            "analysis_count": 0,
            "warning_count": 0,
            "anomaly_count": 0,
            "normal_cycle_count": 0,
            "degraded_cycle_count": 0,
            "failed_cycle_count": 0,
            "publish_error_count": 0,
            "controller_status_error_count": 0,
            "last_event_type": None,
            "last_event_at": None,
            "last_session_id": None,
            "last_quality_score": None,
            "last_classification": None,
            "last_error": None,
        }

        for index, event_type in enumerate(
            self.OBSERVED_EVENT_TYPES,
            start=1,
        ):
            subscription_id = (
                f"c0151-execution-analyzer-{index}"
            )

            actual_id = (
                self.subscription_manager.subscribe(
                    event_type,
                    self._consume,
                    subscription_id=subscription_id,
                )
            )

            self._subscriptions.append(actual_id)

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _normalize_text(value: Any) -> str:
        if value is None:
            return ""

        return (
            str(value)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    @classmethod
    def _json_safe(cls, value: Any) -> Any:
        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            return value

        if isinstance(value, dict):
            return {
                str(key): cls._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                cls._json_safe(item)
                for item in value
            ]

        isoformat = getattr(value, "isoformat", None)

        if callable(isoformat):
            try:
                return isoformat()
            except Exception:
                pass

        value_attribute = getattr(value, "value", None)

        if isinstance(
            value_attribute,
            (bool, int, float, str),
        ):
            return value_attribute

        return repr(value)

    @staticmethod
    def _extract_payload(event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("payload", event)

        payload = getattr(event, "payload", None)

        if payload is not None:
            return payload

        return event

    @staticmethod
    def _parse_datetime(
        value: Any,
    ) -> datetime | None:
        if value is None:
            return None

        if isinstance(value, datetime):
            result = value
        else:
            try:
                result = datetime.fromisoformat(
                    str(value).replace(
                        "Z",
                        "+00:00",
                    )
                )
            except Exception:
                return None

        if result.tzinfo is None:
            result = result.replace(
                tzinfo=timezone.utc
            )

        return result

    @classmethod
    def _seconds_between(
        cls,
        start: Any,
        end: Any,
    ) -> float | None:
        start_dt = cls._parse_datetime(start)
        end_dt = cls._parse_datetime(end)

        if start_dt is None or end_dt is None:
            return None

        return max(
            0.0,
            (end_dt - start_dt).total_seconds(),
        )

    @staticmethod
    def _extract_session(
        payload: Any,
    ) -> dict[str, Any] | None:
        if not isinstance(payload, dict):
            return None

        session = payload.get("session")

        if isinstance(session, dict):
            return session

        if "session_id" in payload:
            return payload

        cancelled = payload.get(
            "cancelled_session"
        )

        if isinstance(cancelled, dict):
            return cancelled

        return None

    def _controller_status(
        self,
    ) -> dict[str, Any]:
        try:
            status = self.controller.status()

            if isinstance(status, dict):
                self._metrics["last_error"] = None
                return self._json_safe(status)

            raise TypeError(
                "controller.status() n'a pas retourné "
                "un dictionnaire."
            )

        except Exception as exc:
            self._metrics[
                "controller_status_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

            return {
                "available": False,
                "error": repr(exc),
            }

    @staticmethod
    def _controller_view(
        status: dict[str, Any],
    ) -> dict[str, Any]:
        if status.get("available") is False:
            return status

        device = status.get("device")

        if not isinstance(device, dict):
            device = {}

        safety = status.get("safety")

        if not isinstance(safety, dict):
            safety = {}

        thermal = status.get("thermal")

        if not isinstance(thermal, dict):
            thermal = {}

        anti_short_cycle = status.get(
            "anti_short_cycle"
        )

        if not isinstance(
            anti_short_cycle,
            dict,
        ):
            anti_short_cycle = {}

        configuration = status.get(
            "configuration"
        )

        if not isinstance(configuration, dict):
            configuration = {}

        return {
            "state": status.get("state"),
            "mode": status.get("mode"),
            "simulation": status.get(
                "simulation"
            ),
            "driver_name": status.get(
                "driver_name"
            ),
            "valve_open": status.get(
                "valve_open"
            ),
            "pump_running": status.get(
                "pump_running"
            ),
            "runtime_seconds": status.get(
                "runtime_seconds"
            ),
            "cycle_count": status.get(
                "cycle_count"
            ),
            "last_event": status.get(
                "last_event"
            ),
            "last_reason": status.get(
                "last_reason"
            ),
            "last_error": status.get(
                "last_error"
            ),
            "device": {
                "ready": device.get("ready"),
                "connected": device.get(
                    "connected"
                ),
                "online": device.get("online"),
                "heartbeat_fresh": device.get(
                    "heartbeat_fresh"
                ),
                "simulation": device.get(
                    "simulation"
                ),
                "reason": device.get("reason"),
            },
            "safety": {
                "safe": safety.get("safe"),
                "level": safety.get("level"),
                "reason": safety.get("reason"),
                "dew_point_c": safety.get(
                    "dew_point_c"
                ),
                "surface_temperature_c":
                    safety.get(
                        "surface_temperature_c"
                    ),
                "margin_c": safety.get(
                    "margin_c"
                ),
            },
            "thermal": {
                "available": thermal.get(
                    "available"
                ),
                "reason": thermal.get("reason"),
                "history_count": thermal.get(
                    "history_count"
                ),
                "energy_transferred_kwh":
                    thermal.get(
                        "energy_transferred_kwh"
                    ),
            },
            "anti_short_cycle":
                anti_short_cycle,
            "configuration": {
                "valve_open_delay_seconds":
                    configuration.get(
                        "valve_open_delay_seconds"
                    ),
                "valve_close_delay_seconds":
                    configuration.get(
                        "valve_close_delay_seconds"
                    ),
                "max_runtime_seconds":
                    configuration.get(
                        "max_runtime_seconds"
                    ),
                "minimum_on_seconds":
                    configuration.get(
                        "minimum_on_seconds"
                    ),
                "minimum_off_seconds":
                    configuration.get(
                        "minimum_off_seconds"
                    ),
                "watchdog_interval_seconds":
                    configuration.get(
                        "watchdog_interval_seconds"
                    ),
                "minimum_dew_point_margin_c":
                    configuration.get(
                        "minimum_dew_point_margin_c"
                    ),
                "require_thermal_sensors":
                    configuration.get(
                        "require_thermal_sensors"
                    ),
            },
        }

    def _new_cycle(
        self,
        *,
        session_id: str,
        session: dict[str, Any],
        received_at: str,
    ) -> dict[str, Any]:
        return {
            "session_id": session_id,
            "created_at": received_at,
            "updated_at": received_at,
            "terminal_at": None,
            "last_event_type": None,
            "last_event_at": None,
            "event_count": 0,
            "event_order": [],
            "timestamps": {
                "started": None,
                "running": None,
                "stopping": None,
                "completed": None,
                "failed": None,
                "reset": None,
            },
            "session": self._json_safe(session),
            "controller_snapshots": [],
            "transition_warnings": [],
            "duplicate_events": [],
        }

    def _record_event(
        self,
        *,
        cycle: dict[str, Any],
        event_type: str,
        received_at: str,
        session: dict[str, Any],
        controller_view: dict[str, Any],
    ) -> None:
        previous_event = cycle.get(
            "last_event_type"
        )

        allowed = self.EXPECTED_TRANSITIONS.get(
            previous_event,
            set(),
        )

        if event_type not in allowed:
            warning = {
                "type": "unexpected_transition",
                "from": previous_event,
                "to": event_type,
                "at": received_at,
            }

            cycle[
                "transition_warnings"
            ].append(warning)

        if event_type in cycle["event_order"]:
            duplicate = {
                "event_type": event_type,
                "at": received_at,
            }

            cycle["duplicate_events"].append(
                duplicate
            )

        cycle["event_count"] += 1
        cycle["event_order"].append(event_type)
        cycle["last_event_type"] = event_type
        cycle["last_event_at"] = received_at
        cycle["updated_at"] = received_at
        cycle["session"] = self._json_safe(
            session
        )

        timestamp_key = {
            "execution.started": "started",
            "execution.running": "running",
            "execution.stopping": "stopping",
            "execution.completed": "completed",
            "execution.failed": "failed",
            "execution.reset": "reset",
        }.get(event_type)

        if timestamp_key:
            cycle["timestamps"][
                timestamp_key
            ] = received_at

        cycle["controller_snapshots"].append(
            {
                "event_type": event_type,
                "captured_at": received_at,
                "controller":
                    self._json_safe(
                        controller_view
                    ),
            }
        )

        if event_type in self.TERMINAL_EVENT_TYPES:
            cycle["terminal_at"] = received_at

    @staticmethod
    def _phase_durations(
        timestamps: dict[str, Any],
    ) -> dict[str, float | None]:
        started = timestamps.get("started")
        running = timestamps.get("running")
        stopping = timestamps.get("stopping")

        terminal = (
            timestamps.get("completed")
            or timestamps.get("failed")
            or timestamps.get("reset")
        )

        return {
            "start_transition_seconds":
                GeoCoolingExecutionAnalyzer
                ._seconds_between(
                    started,
                    running,
                ),
            "running_seconds":
                GeoCoolingExecutionAnalyzer
                ._seconds_between(
                    running,
                    stopping or terminal,
                ),
            "stop_transition_seconds":
                GeoCoolingExecutionAnalyzer
                ._seconds_between(
                    stopping,
                    terminal,
                ),
            "total_seconds":
                GeoCoolingExecutionAnalyzer
                ._seconds_between(
                    started,
                    terminal,
                ),
        }

    @staticmethod
    def _latest_controller_snapshot(
        cycle: dict[str, Any],
    ) -> dict[str, Any]:
        snapshots = cycle.get(
            "controller_snapshots"
        )

        if not isinstance(snapshots, list):
            return {}

        if not snapshots:
            return {}

        latest = snapshots[-1]

        if not isinstance(latest, dict):
            return {}

        controller = latest.get("controller")

        if not isinstance(controller, dict):
            return {}

        return controller

    @staticmethod
    def _first_controller_snapshot(
        cycle: dict[str, Any],
    ) -> dict[str, Any]:
        snapshots = cycle.get(
            "controller_snapshots"
        )

        if not isinstance(snapshots, list):
            return {}

        if not snapshots:
            return {}

        first = snapshots[0]

        if not isinstance(first, dict):
            return {}

        controller = first.get("controller")

        if not isinstance(controller, dict):
            return {}

        return controller

    def _evaluate_cycle(
        self,
        cycle: dict[str, Any],
    ) -> dict[str, Any]:
        warnings: list[dict[str, Any]] = []
        anomalies: list[dict[str, Any]] = []
        recommendations: list[str] = []

        score = 100

        timestamps = cycle["timestamps"]
        phase_durations = self._phase_durations(
            timestamps
        )

        session = cycle.get("session")

        if not isinstance(session, dict):
            session = {}

        latest = self._latest_controller_snapshot(
            cycle
        )

        first = self._first_controller_snapshot(
            cycle
        )

        event_order = cycle.get(
            "event_order",
            [],
        )

        transition_warnings = cycle.get(
            "transition_warnings",
            [],
        )

        duplicate_events = cycle.get(
            "duplicate_events",
            [],
        )

        if transition_warnings:
            score -= min(
                30,
                len(transition_warnings) * 10,
            )

            anomalies.extend(
                transition_warnings
            )

        if duplicate_events:
            score -= min(
                15,
                len(duplicate_events) * 5,
            )

            warnings.append(
                {
                    "type": "duplicate_events",
                    "count": len(
                        duplicate_events
                    ),
                    "events": duplicate_events,
                }
            )

        terminal_event = (
            cycle.get("last_event_type")
        )

        if terminal_event == "execution.failed":
            score -= 50

            anomalies.append(
                {
                    "type": "execution_failed",
                    "reason": session.get(
                        "reason"
                    ),
                    "result": session.get(
                        "result"
                    ),
                }
            )

        elif terminal_event == "execution.reset":
            score -= 30

            warnings.append(
                {
                    "type": "execution_reset",
                    "reason": session.get(
                        "reason"
                    ),
                }
            )

        if (
            terminal_event
            == "execution.completed"
            and "execution.stopping"
            not in event_order
        ):
            score -= 20

            anomalies.append(
                {
                    "type":
                        "completion_without_stopping",
                }
            )

        if (
            "execution.running" in event_order
            and "execution.started"
            not in event_order
        ):
            score -= 20

            anomalies.append(
                {
                    "type":
                        "running_without_started",
                }
            )

        device = latest.get("device")

        if not isinstance(device, dict):
            device = {}

        if device.get("ready") is False:
            score -= 20

            anomalies.append(
                {
                    "type": "device_not_ready",
                    "reason": device.get(
                        "reason"
                    ),
                }
            )

        if device.get("connected") is False:
            score -= 20

            anomalies.append(
                {
                    "type":
                        "device_disconnected",
                }
            )

        if device.get("online") is False:
            score -= 20

            anomalies.append(
                {
                    "type": "device_offline",
                }
            )

        if device.get(
            "heartbeat_fresh"
        ) is False:
            score -= 15

            warnings.append(
                {
                    "type":
                        "heartbeat_not_fresh",
                }
            )

        safety = latest.get("safety")

        if not isinstance(safety, dict):
            safety = {}

        if safety.get("safe") is False:
            score -= 40

            anomalies.append(
                {
                    "type":
                        "thermal_safety_unsafe",
                    "level": safety.get(
                        "level"
                    ),
                    "reason": safety.get(
                        "reason"
                    ),
                }
            )

        elif (
            self._normalize_text(
                safety.get("level")
            )
            == "unavailable"
        ):
            score -= 5

            warnings.append(
                {
                    "type":
                        "thermal_safety_unavailable",
                    "reason": safety.get(
                        "reason"
                    ),
                }
            )

        thermal = latest.get("thermal")

        if not isinstance(thermal, dict):
            thermal = {}

        if thermal.get("available") is False:
            score -= 5

            warnings.append(
                {
                    "type":
                        "thermal_measurements_unavailable",
                    "reason": thermal.get(
                        "reason"
                    ),
                }
            )

        simulation = bool(
            latest.get("simulation")
        )

        if simulation:
            warnings.append(
                {
                    "type": "simulation_cycle",
                    "reason":
                        "Cycle analysé en simulation.",
                }
            )

        terminal_state = self._normalize_text(
            latest.get("state")
        )

        terminal_pump = latest.get(
            "pump_running"
        )

        terminal_valve = latest.get(
            "valve_open"
        )

        if terminal_event in {
            "execution.completed",
            "execution.reset",
        }:
            if terminal_state not in {
                "",
                "off",
            }:
                score -= 15

                warnings.append(
                    {
                        "type":
                            "controller_not_off_after_terminal_event",
                        "state": latest.get(
                            "state"
                        ),
                    }
                )

            if terminal_pump is True:
                score -= 30

                anomalies.append(
                    {
                        "type":
                            "pump_running_after_terminal_event",
                    }
                )

            if terminal_valve is True:
                score -= 20

                anomalies.append(
                    {
                        "type":
                            "valve_open_after_terminal_event",
                    }
                )

        initial_state = self._normalize_text(
            first.get("state")
        )

        if (
            "execution.started" in event_order
            and initial_state not in {
                "",
                "off",
                "opening_valve",
                "waiting_flow",
                "starting_pump",
                "running",
            }
        ):
            score -= 10

            warnings.append(
                {
                    "type":
                        "unexpected_controller_state_at_start",
                    "state": first.get("state"),
                }
            )

        configuration = latest.get(
            "configuration"
        )

        if not isinstance(configuration, dict):
            configuration = {}

        total_seconds = phase_durations.get(
            "total_seconds"
        )

        max_runtime_seconds = configuration.get(
            "max_runtime_seconds"
        )

        try:
            max_runtime_value = float(
                max_runtime_seconds
            )
        except (
            TypeError,
            ValueError,
        ):
            max_runtime_value = None

        if (
            total_seconds is not None
            and max_runtime_value is not None
            and total_seconds
            > max_runtime_value
        ):
            score -= 40

            anomalies.append(
                {
                    "type":
                        "maximum_runtime_exceeded",
                    "duration_seconds":
                        total_seconds,
                    "maximum_seconds":
                        max_runtime_value,
                }
            )

        minimum_on_seconds = configuration.get(
            "minimum_on_seconds"
        )

        try:
            minimum_on_value = float(
                minimum_on_seconds
            )
        except (
            TypeError,
            ValueError,
        ):
            minimum_on_value = None

        running_seconds = phase_durations.get(
            "running_seconds"
        )

        if (
            terminal_event
            == "execution.completed"
            and running_seconds is not None
            and minimum_on_value is not None
            and running_seconds
            < minimum_on_value
            and not simulation
        ):
            score -= 15

            warnings.append(
                {
                    "type":
                        "runtime_below_minimum_on_time",
                    "runtime_seconds":
                        running_seconds,
                    "minimum_seconds":
                        minimum_on_value,
                }
            )

        start_transition_seconds = (
            phase_durations.get(
                "start_transition_seconds"
            )
        )

        valve_open_delay = configuration.get(
            "valve_open_delay_seconds"
        )

        try:
            valve_delay_value = float(
                valve_open_delay
            )
        except (
            TypeError,
            ValueError,
        ):
            valve_delay_value = None

        if (
            start_transition_seconds
            is not None
            and valve_delay_value is not None
            and start_transition_seconds
            > max(
                30.0,
                valve_delay_value * 5,
            )
        ):
            score -= 10

            warnings.append(
                {
                    "type":
                        "slow_start_transition",
                    "duration_seconds":
                        start_transition_seconds,
                    "expected_valve_delay_seconds":
                        valve_delay_value,
                }
            )

        stop_transition_seconds = (
            phase_durations.get(
                "stop_transition_seconds"
            )
        )

        valve_close_delay = configuration.get(
            "valve_close_delay_seconds"
        )

        try:
            valve_close_value = float(
                valve_close_delay
            )
        except (
            TypeError,
            ValueError,
        ):
            valve_close_value = None

        if (
            stop_transition_seconds
            is not None
            and valve_close_value is not None
            and stop_transition_seconds
            > max(
                30.0,
                valve_close_value * 5,
            )
        ):
            score -= 10

            warnings.append(
                {
                    "type":
                        "slow_stop_transition",
                    "duration_seconds":
                        stop_transition_seconds,
                    "expected_valve_close_delay_seconds":
                        valve_close_value,
                }
            )

        if anomalies:
            recommendations.append(
                "Contrôler les anomalies avant "
                "d'autoriser un pilotage matériel."
            )

        if any(
            item.get("type")
            == "thermal_measurements_unavailable"
            for item in warnings
        ):
            recommendations.append(
                "Raccorder et valider les sondes "
                "hydrauliques avant l'analyse "
                "thermique avancée."
            )

        if simulation:
            recommendations.append(
                "Valider ensuite le même scénario "
                "avec le driver MQTT, bridge toujours "
                "désarmé."
            )

        if not recommendations:
            recommendations.append(
                "Cycle cohérent. Aucune correction "
                "immédiate nécessaire."
            )

        score = max(
            0,
            min(
                100,
                int(round(score)),
            ),
        )

        if terminal_event == "execution.failed":
            classification = "FAILED"

        elif anomalies:
            classification = "ANOMALOUS"

        elif score >= 90:
            classification = "NORMAL"

        elif score >= 70:
            classification = "ACCEPTABLE"

        elif score >= 50:
            classification = "DEGRADED"

        else:
            classification = "CRITICAL"

        return {
            "analysis_id": (
                f"{cycle['session_id']}:"
                f"{cycle['terminal_at'] or cycle['updated_at']}"
            ),
            "session_id": cycle["session_id"],
            "generated_at": self._utc_now(),
            "terminal_event": terminal_event,
            "classification": classification,
            "quality_score": score,
            "phase_durations":
                phase_durations,
            "event_order": list(event_order),
            "event_count": cycle.get(
                "event_count",
                0,
            ),
            "warnings": warnings,
            "anomalies": anomalies,
            "recommendations":
                recommendations,
            "warning_count": len(warnings),
            "anomaly_count": len(anomalies),
            "simulation": simulation,
            "session":
                self._json_safe(session),
            "controller_start":
                self._json_safe(first),
            "controller_terminal":
                self._json_safe(latest),
        }

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
                source="execution-analyzer",
                payload=self._json_safe(payload),
                level=level,
            )

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "publish_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def _finalize(
        self,
        cycle: dict[str, Any],
    ) -> dict[str, Any]:
        analysis = self._evaluate_cycle(cycle)

        self._analyses.append(
            deepcopy(analysis)
        )

        self._metrics["analysis_count"] += 1
        self._metrics["warning_count"] += (
            analysis["warning_count"]
        )
        self._metrics["anomaly_count"] += (
            analysis["anomaly_count"]
        )

        classification = analysis[
            "classification"
        ]

        if classification == "NORMAL":
            self._metrics[
                "normal_cycle_count"
            ] += 1

        elif classification == "FAILED":
            self._metrics[
                "failed_cycle_count"
            ] += 1

        elif classification in {
            "DEGRADED",
            "CRITICAL",
            "ANOMALOUS",
        }:
            self._metrics[
                "degraded_cycle_count"
            ] += 1

        self._metrics[
            "last_quality_score"
        ] = analysis["quality_score"]

        self._metrics[
            "last_classification"
        ] = classification

        level = "INFO"

        if classification in {
            "DEGRADED",
            "ANOMALOUS",
        }:
            level = "WARN"

        elif classification in {
            "FAILED",
            "CRITICAL",
        }:
            level = "ERROR"

        self._publish(
            event_type="execution.analysis",
            payload=analysis,
            level=level,
        )

        if (
            analysis["warning_count"] > 0
            or analysis["anomaly_count"] > 0
        ):
            self._publish(
                event_type=(
                    "execution.analysis.warning"
                ),
                payload={
                    "session_id":
                        analysis["session_id"],
                    "classification":
                        classification,
                    "quality_score":
                        analysis["quality_score"],
                    "warnings":
                        analysis["warnings"],
                    "anomalies":
                        analysis["anomalies"],
                },
                level=(
                    "ERROR"
                    if analysis[
                        "anomaly_count"
                    ] > 0
                    else "WARN"
                ),
            )

        return analysis

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        received_at = self._utc_now()
        payload = self._extract_payload(event)
        session = self._extract_session(payload)

        with self._lock:
            self._metrics[
                "received_count"
            ] += 1
            self._metrics[
                "last_event_type"
            ] = event_type
            self._metrics[
                "last_event_at"
            ] = received_at

            if not isinstance(session, dict):
                self._metrics[
                    "ignored_count"
                ] += 1

                self._events.append(
                    {
                        "timestamp": received_at,
                        "event_type": event_type,
                        "processed": False,
                        "reason":
                            "Session absente",
                        "payload":
                            self._json_safe(payload),
                    }
                )

                return

            session_id = session.get(
                "session_id"
            )

            if not session_id:
                self._metrics[
                    "ignored_count"
                ] += 1

                self._events.append(
                    {
                        "timestamp": received_at,
                        "event_type": event_type,
                        "processed": False,
                        "reason":
                            "session_id absent",
                        "payload":
                            self._json_safe(payload),
                    }
                )

                return

            session_id = str(session_id)

            self._metrics[
                "processed_count"
            ] += 1
            self._metrics[
                "last_session_id"
            ] = session_id

            cycle = self._cycles.get(
                session_id
            )

            if cycle is None:
                cycle = self._new_cycle(
                    session_id=session_id,
                    session=session,
                    received_at=received_at,
                )

                self._cycles[session_id] = cycle

            controller_status = (
                self._controller_status()
            )

            controller_view = (
                self._controller_view(
                    controller_status
                )
            )

            self._record_event(
                cycle=cycle,
                event_type=event_type,
                received_at=received_at,
                session=session,
                controller_view=controller_view,
            )

            self._events.append(
                {
                    "timestamp": received_at,
                    "event_type": event_type,
                    "session_id": session_id,
                    "processed": True,
                    "controller":
                        self._json_safe(
                            controller_view
                        ),
                }
            )

            if event_type in self.TERMINAL_EVENT_TYPES:
                self._finalize(cycle)

                self._cycles.pop(
                    session_id,
                    None,
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            active_cycles = [
                {
                    "session_id":
                        cycle["session_id"],
                    "created_at":
                        cycle["created_at"],
                    "updated_at":
                        cycle["updated_at"],
                    "last_event_type":
                        cycle[
                            "last_event_type"
                        ],
                    "event_count":
                        cycle["event_count"],
                    "event_order":
                        list(
                            cycle["event_order"]
                        ),
                }
                for cycle in self._cycles.values()
            ]

            return {
                "overall": "OK",
                "component":
                    "execution_analyzer",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "started_at": self._started_at,
                "subscriptions": list(
                    self._subscriptions
                ),
                "observed_event_types": list(
                    self.OBSERVED_EVENT_TYPES
                ),
                "active_cycle_count":
                    len(self._cycles),
                "active_cycles":
                    active_cycles,
                "analysis_history_count":
                    len(self._analyses),
                "event_history_count":
                    len(self._events),
                "metrics":
                    dict(self._metrics),
            }

    def history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        normalized_limit = max(
            1,
            min(
                int(limit),
                self.history_capacity,
            ),
        )

        with self._lock:
            analyses = list(
                self._analyses
            )[-normalized_limit:]

        return {
            "overall": "OK",
            "component":
                "execution_analyzer",
            "limit": normalized_limit,
            "count": len(analyses),
            "analyses": deepcopy(analyses),
        }

    def latest(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            analysis = (
                deepcopy(self._analyses[-1])
                if self._analyses
                else None
            )

        return {
            "overall": "OK",
            "component":
                "execution_analyzer",
            "available": analysis is not None,
            "analysis": analysis,
        }

    def event_history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        normalized_limit = max(
            1,
            min(
                int(limit),
                self.event_capacity,
            ),
        )

        with self._lock:
            events = list(
                self._events
            )[-normalized_limit:]

        return {
            "overall": "OK",
            "component":
                "execution_analyzer",
            "limit": normalized_limit,
            "count": len(events),
            "events": deepcopy(events),
        }
