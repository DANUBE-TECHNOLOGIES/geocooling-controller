"""
C014.2R2 — Barrière de sécurité avant exécution Controller.

Entrée :
    brain.command

Sorties :
    controller.command.approved
    controller.command.rejected
"""

from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


class GeoCoolingControllerSafetyGate:
    """Valide toute commande avant transmission au bridge."""

    PATCH_VERSION = "C014.2R2"
    SUBSCRIPTION_ID = "c0142-controller-safety-gate"

    FAIL_SAFE_ACTIONS = {
        "stop",
        "emergency_stop",
    }

    CONTROLLED_ACTIONS = {
        "start",
        "reset",
    }

    def __init__(
        self,
        *,
        controller: Any,
        state_cache: Any,
        subscription_manager: Any,
        event_bus: Any,
        maximum_thermal_age_seconds: float = 180.0,
        minimum_confidence: float = 0.0,
        minimum_data_quality: float = 0.0,
        history_capacity: int = 500,
    ) -> None:
        self.controller = controller
        self.state_cache = state_cache
        self.subscription_manager = (
            subscription_manager
        )
        self.event_bus = event_bus

        self.maximum_thermal_age_seconds = max(
            1.0,
            float(maximum_thermal_age_seconds),
        )

        self.minimum_confidence = max(
            0.0,
            float(minimum_confidence),
        )

        self.minimum_data_quality = max(
            0.0,
            float(minimum_data_quality),
        )

        self.history_capacity = max(
            50,
            int(history_capacity),
        )

        self._lock = threading.RLock()
        self._started_at = self._utc_now()

        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._metrics = {
            "received_count": 0,
            "approved_count": 0,
            "rejected_count": 0,
            "bypassed_fail_safe_count": 0,
            "error_count": 0,
            "last_received_at": None,
            "last_action": None,
            "last_result": None,
            "last_rejection_reasons": [],
            "last_error": None,
        }

        self._subscription_id = (
            self.subscription_manager.subscribe(
                "brain.command",
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
    def _normalize_action(value: Any) -> str:
        if value is None:
            return ""

        return (
            str(value)
            .strip()
            .lower()
            .replace("-", "_")
            .replace(" ", "_")
        )

    @staticmethod
    def _to_float(value: Any) -> float | None:
        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return float(value)

        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass

        return None

    def _append_history(
        self,
        entry: dict[str, Any],
    ) -> None:
        with self._lock:
            self._history.append(
                self._json_safe(entry)
            )

    def _controller_status(
        self,
    ) -> dict[str, Any]:
        status_method = getattr(
            self.controller,
            "status",
            None,
        )

        if not callable(status_method):
            raise RuntimeError(
                "controller.status indisponible"
            )

        status = status_method()

        if not isinstance(status, dict):
            raise RuntimeError(
                "controller.status invalide"
            )

        return status

    def _cache_status(
        self,
    ) -> dict[str, Any]:
        status_method = getattr(
            self.state_cache,
            "status",
            None,
        )

        if not callable(status_method):
            raise RuntimeError(
                "state_cache.status indisponible"
            )

        try:
            status = status_method(
                include_controller=False
            )
        except TypeError:
            status = status_method()

        if not isinstance(status, dict):
            raise RuntimeError(
                "state_cache.status invalide"
            )

        return status

    def _watchdog_status(
        self,
    ) -> dict[str, Any] | None:
        for method_name in (
            "watchdog_status",
            "get_watchdog_status",
        ):
            method = getattr(
                self.controller,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                result = method()

                if isinstance(result, dict):
                    return result
            except Exception:
                return None

        watchdog = getattr(
            self.controller,
            "watchdog",
            None,
        )

        if watchdog is not None:
            status_method = getattr(
                watchdog,
                "status",
                None,
            )

            if callable(status_method):
                try:
                    result = status_method()

                    if isinstance(result, dict):
                        return result
                except Exception:
                    return None

        return None

    def _evaluate(
        self,
        command: dict[str, Any],
    ) -> dict[str, Any]:
        action = self._normalize_action(
            command.get("action")
        )

        checks: list[dict[str, Any]] = []
        rejection_reasons: list[str] = []

        def add_check(
            *,
            code: str,
            passed: bool,
            message: str,
            blocking: bool = True,
            details: dict[str, Any] | None = None,
        ) -> None:
            checks.append(
                {
                    "code": code,
                    "passed": bool(passed),
                    "blocking": bool(blocking),
                    "message": message,
                    "details": details or {},
                }
            )

            if blocking and not passed:
                rejection_reasons.append(
                    f"{code}: {message}"
                )

        if action in self.FAIL_SAFE_ACTIONS:
            add_check(
                code="fail_safe_action",
                passed=True,
                blocking=False,
                message=(
                    "Commande d'arrêt autorisée "
                    "sans condition préalable."
                ),
                details={
                    "action": action,
                },
            )

            return {
                "approved": True,
                "fail_safe_bypass": True,
                "checks": checks,
                "rejection_reasons": [],
            }

        if action == "wait":
            add_check(
                code="non_executable_wait",
                passed=False,
                blocking=True,
                message=(
                    "WAIT ne constitue pas une "
                    "commande Controller."
                ),
            )

            return {
                "approved": False,
                "fail_safe_bypass": False,
                "checks": checks,
                "rejection_reasons":
                    rejection_reasons,
            }

        if action not in self.CONTROLLED_ACTIONS:
            add_check(
                code="supported_action",
                passed=False,
                message=(
                    f"Action non prise en charge : "
                    f"{action or 'vide'}"
                ),
            )

            return {
                "approved": False,
                "fail_safe_bypass": False,
                "checks": checks,
                "rejection_reasons":
                    rejection_reasons,
            }

        controller_status = (
            self._controller_status()
        )

        cache_status = self._cache_status()
        watchdog_status = self._watchdog_status()

        simulation = bool(
            controller_status.get("simulation")
            or str(
                controller_status.get(
                    "mode",
                    "",
                )
            ).upper() == "SIMULATION"
        )

        add_check(
            code="state_cache_running",
            passed=bool(
                cache_status.get("running")
            ),
            message=(
                "StateCache actif."
                if cache_status.get("running")
                else "StateCache arrêté."
            ),
        )

        add_check(
            code="state_cache_ready",
            passed=bool(
                cache_status.get("ready")
            ),
            message=(
                "StateCache prêt."
                if cache_status.get("ready")
                else "StateCache non prêt."
            ),
        )

        snapshot = cache_status.get(
            "snapshot"
        ) or {}

        cache_stale = bool(
            snapshot.get(
                "stale",
                cache_status.get("stale", True),
            )
        )

        add_check(
            code="state_cache_fresh",
            passed=not cache_stale,
            message=(
                "Snapshot StateCache récent."
                if not cache_stale
                else "Snapshot StateCache périmé."
            ),
            details={
                "age_seconds":
                    snapshot.get("age_seconds"),
            },
        )

        device = controller_status.get(
            "device"
        ) or {}

        add_check(
            code="device_ready",
            passed=bool(
                simulation
                or device.get("ready")
            ),
            message=(
                "Driver prêt."
                if simulation
                or device.get("ready")
                else "Driver non prêt."
            ),
            details={
                "simulation": simulation,
                "ready": device.get("ready"),
            },
        )

        add_check(
            code="device_online",
            passed=bool(
                simulation
                or device.get("online")
            ),
            message=(
                "Équipement en ligne."
                if simulation
                or device.get("online")
                else "Équipement hors ligne."
            ),
            details={
                "simulation": simulation,
                "online": device.get("online"),
            },
        )

        add_check(
            code="heartbeat_fresh",
            passed=bool(
                simulation
                or device.get("heartbeat_fresh")
            ),
            message=(
                "Heartbeat valide."
                if simulation
                or device.get("heartbeat_fresh")
                else "Heartbeat absent ou périmé."
            ),
            details={
                "simulation": simulation,
                "heartbeat_fresh":
                    device.get("heartbeat_fresh"),
            },
        )

        safety = controller_status.get(
            "safety"
        ) or {}

        safety_safe = bool(
            safety.get("safe")
        )

        add_check(
            code="thermal_safety",
            passed=safety_safe,
            message=(
                "Sécurité thermique satisfaite."
                if safety_safe
                else "Sécurité thermique refusée."
            ),
            details={
                "level": safety.get("level"),
                "reason": safety.get("reason"),
                "dew_point_c":
                    safety.get("dew_point_c"),
                "surface_temperature_c":
                    safety.get(
                        "surface_temperature_c"
                    ),
                "margin_c":
                    safety.get("margin_c"),
            },
        )

        safety_level = str(
            safety.get("level", "")
        ).upper()

        add_check(
            code="thermal_measurements_complete",
            passed=bool(
                simulation
                or safety_level not in (
                    "",
                    "UNAVAILABLE",
                )
            ),
            blocking=not simulation,
            message=(
                "Mesures thermiques suffisantes."
                if safety_level not in (
                    "",
                    "UNAVAILABLE",
                )
                else (
                    "Mesures thermiques "
                    "incomplètes."
                )
            ),
            details={
                "simulation": simulation,
                "level": safety_level,
            },
        )

        thermal = controller_status.get(
            "thermal"
        ) or {}

        latest = thermal.get("latest") or {}

        thermal_timestamp = latest.get(
            "timestamp"
        )

        thermal_age_seconds = None

        if thermal_timestamp:
            try:
                timestamp = datetime.fromisoformat(
                    str(thermal_timestamp)
                    .replace("Z", "+00:00")
                )

                if timestamp.tzinfo is None:
                    timestamp = timestamp.replace(
                        tzinfo=timezone.utc
                    )

                thermal_age_seconds = max(
                    0.0,
                    (
                        datetime.now(timezone.utc)
                        - timestamp
                    ).total_seconds(),
                )
            except Exception:
                thermal_age_seconds = None

        thermal_fresh = bool(
            thermal_age_seconds is not None
            and thermal_age_seconds
            <= self.maximum_thermal_age_seconds
        )

        add_check(
            code="thermal_freshness",
            passed=thermal_fresh,
            message=(
                "Données thermiques récentes."
                if thermal_fresh
                else (
                    "Données thermiques absentes "
                    "ou périmées."
                )
            ),
            details={
                "timestamp": thermal_timestamp,
                "age_seconds":
                    thermal_age_seconds,
                "maximum_age_seconds":
                    self.maximum_thermal_age_seconds,
            },
        )

        anti_short_cycle = (
            controller_status.get(
                "anti_short_cycle"
            )
            or {}
        )

        remaining_off = self._to_float(
            anti_short_cycle.get(
                "remaining_minimum_off_seconds"
            )
        )

        if action == "start":
            add_check(
                code="minimum_off_time",
                passed=bool(
                    remaining_off is not None
                    and remaining_off <= 0
                ),
                message=(
                    "Temporisation minimum OFF "
                    "respectée."
                    if remaining_off is not None
                    and remaining_off <= 0
                    else (
                        "Temporisation minimum OFF "
                        "encore active."
                    )
                ),
                details={
                    "remaining_seconds":
                        remaining_off,
                },
            )

        confidence = self._to_float(
            command.get("confidence")
        )

        add_check(
            code="brain_confidence",
            passed=bool(
                confidence is None
                or confidence
                >= self.minimum_confidence
            ),
            message=(
                "Confiance Brain suffisante."
                if confidence is None
                or confidence
                >= self.minimum_confidence
                else "Confiance Brain insuffisante."
            ),
            details={
                "value": confidence,
                "minimum":
                    self.minimum_confidence,
            },
        )

        data_quality = self._to_float(
            command.get("data_quality")
        )

        add_check(
            code="brain_data_quality",
            passed=bool(
                data_quality is None
                or data_quality
                >= self.minimum_data_quality
            ),
            message=(
                "Qualité des données suffisante."
                if data_quality is None
                or data_quality
                >= self.minimum_data_quality
                else (
                    "Qualité des données "
                    "insuffisante."
                )
            ),
            details={
                "value": data_quality,
                "minimum":
                    self.minimum_data_quality,
            },
        )

        watchdog_blocking_alerts = []

        if isinstance(watchdog_status, dict):
            alerts = watchdog_status.get(
                "alerts"
            ) or []

            for alert in alerts:
                if not isinstance(alert, dict):
                    continue

                severity = str(
                    alert.get("severity", "")
                ).upper()

                if severity in (
                    "ERROR",
                    "CRITICAL",
                ):
                    watchdog_blocking_alerts.append(
                        {
                            "code": alert.get("code"),
                            "severity": severity,
                            "message":
                                alert.get("message"),
                        }
                    )

        add_check(
            code="watchdog",
            passed=not watchdog_blocking_alerts,
            message=(
                "Aucune alerte Watchdog bloquante."
                if not watchdog_blocking_alerts
                else (
                    "Alerte Watchdog ERROR ou "
                    "CRITICAL active."
                )
            ),
            details={
                "blocking_alerts":
                    watchdog_blocking_alerts,
                "watchdog_available":
                    watchdog_status is not None,
            },
        )

        return {
            "approved":
                not rejection_reasons,
            "fail_safe_bypass": False,
            "simulation": simulation,
            "checks": checks,
            "rejection_reasons":
                rejection_reasons,
        }

    def _publish(
        self,
        *,
        approved: bool,
        command: dict[str, Any],
        evaluation: dict[str, Any],
    ) -> None:
        event_type = (
            "controller.command.approved"
            if approved
            else "controller.command.rejected"
        )

        level = (
            "INFO"
            if approved
            else "WARN"
        )

        self.event_bus.publish(
            event_type=event_type,
            source="controller-safety-gate",
            payload={
                **self._json_safe(command),
                "safety_gate": {
                    "approved": approved,
                    "evaluated_at":
                        self._utc_now(),
                    **self._json_safe(evaluation),
                },
            },
            level=level,
        )

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        received_at = self._utc_now()
        payload = self._extract_payload(event)

        command = (
            payload
            if isinstance(payload, dict)
            else {
                "action": payload,
            }
        )

        action = self._normalize_action(
            command.get("action")
        )

        with self._lock:
            self._metrics["received_count"] += 1
            self._metrics["last_received_at"] = (
                received_at
            )
            self._metrics["last_action"] = action

        try:
            evaluation = self._evaluate(
                command
            )

            approved = bool(
                evaluation.get("approved")
            )

            self._publish(
                approved=approved,
                command=command,
                evaluation=evaluation,
            )

            with self._lock:
                if approved:
                    self._metrics[
                        "approved_count"
                    ] += 1

                    if evaluation.get(
                        "fail_safe_bypass"
                    ):
                        self._metrics[
                            "bypassed_fail_safe_count"
                        ] += 1

                    self._metrics[
                        "last_result"
                    ] = "approved"

                    self._metrics[
                        "last_rejection_reasons"
                    ] = []

                else:
                    self._metrics[
                        "rejected_count"
                    ] += 1

                    self._metrics[
                        "last_result"
                    ] = "rejected"

                    self._metrics[
                        "last_rejection_reasons"
                    ] = list(
                        evaluation.get(
                            "rejection_reasons",
                            [],
                        )
                    )

                self._metrics["last_error"] = None

            self._append_history(
                {
                    "received_at": received_at,
                    "command_id":
                        command.get("command_id"),
                    "action": action,
                    "result": (
                        "approved"
                        if approved
                        else "rejected"
                    ),
                    "evaluation": evaluation,
                }
            )

        except Exception as exc:
            with self._lock:
                self._metrics["error_count"] += 1
                self._metrics["last_result"] = "error"
                self._metrics["last_error"] = repr(
                    exc
                )

            self._append_history(
                {
                    "received_at": received_at,
                    "command_id":
                        command.get("command_id"),
                    "action": action,
                    "result": "error",
                    "error": repr(exc),
                }
            )

            try:
                self.event_bus.publish(
                    event_type=(
                        "controller.command.rejected"
                    ),
                    source="controller-safety-gate",
                    payload={
                        **self._json_safe(command),
                        "safety_gate": {
                            "approved": False,
                            "evaluated_at":
                                self._utc_now(),
                            "rejection_reasons": [
                                (
                                    "Erreur interne "
                                    f"Safety Gate : {exc!r}"
                                )
                            ],
                        },
                    },
                    level="ERROR",
                )
            except Exception:
                pass

    def evaluate_current(
        self,
        *,
        action: str = "start",
    ) -> dict[str, Any]:
        command = {
            "command_id": "manual-evaluation",
            "action": self._normalize_action(
                action
            ),
            "confidence": 100,
            "data_quality": 100,
        }

        evaluation = self._evaluate(
            command
        )

        return {
            "overall": (
                "OK"
                if evaluation["approved"]
                else "BLOCKED"
            ),
            "component":
                "controller_safety_gate",
            "command": command,
            "evaluation": evaluation,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "overall": "OK",
                "component":
                    "controller_safety_gate",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "subscription_id":
                    self._subscription_id,
                "started_at": self._started_at,
                "configuration": {
                    "maximum_thermal_age_seconds":
                        self.maximum_thermal_age_seconds,
                    "minimum_confidence":
                        self.minimum_confidence,
                    "minimum_data_quality":
                        self.minimum_data_quality,
                    "history_capacity":
                        self.history_capacity,
                    "warning_alerts_blocking":
                        False,
                    "error_alerts_blocking":
                        True,
                    "critical_alerts_blocking":
                        True,
                    "physical_mode_requires_complete_thermal":
                        True,
                    "simulation_allows_incomplete_thermal":
                        True,
                },
                "history_size":
                    len(self._history),
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
            history = list(
                self._history
            )[-normalized_limit:]

        return {
            "overall": "OK",
            "component":
                "controller_safety_gate",
            "limit": normalized_limit,
            "count": len(history),
            "history": history,
        }
