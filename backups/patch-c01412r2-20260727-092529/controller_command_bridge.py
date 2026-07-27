"""
C014.0R1 — Pont événementiel Brain → GeoCoolingController.

Le composant écoute les événements ``brain.decision`` et traduit
les décisions reconnues en appels sécurisés vers le Controller.

Le bridge est volontairement désarmé au démarrage.
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any


class GeoCoolingControllerCommandBridge:
    """Consomme les décisions du Brain et pilote le Controller."""

    PATCH_VERSION = "C014.0R1"
    SUBSCRIPTION_ID = "c0140-controller-command-bridge"

    ACTION_METHODS = {
        "start": "request_start",
        "on": "request_start",
        "enable": "request_start",
        "cool": "request_start",
        "cooling": "request_start",
        "request_start": "request_start",

        "stop": "request_stop",
        "off": "request_stop",
        "disable": "request_stop",
        "idle": "request_stop",
        "request_stop": "request_stop",

        "emergency_stop": "emergency_stop",
        "emergency": "emergency_stop",
        "abort": "emergency_stop",

        "reset": "reset",
    }

    IGNORED_ACTIONS = {
        "",
        "none",
        "noop",
        "no_op",
        "hold",
        "maintain",
        "wait",
        "observe",
        "monitor",
        "unknown",
    }

    def __init__(
        self,
        *,
        controller: Any,
        subscription_manager: Any,
        event_bus: Any,
        armed: bool = False,
        cooldown_seconds: float = 30.0,
        deduplication_seconds: float = 10.0,
        history_capacity: int = 500,
    ) -> None:
        self.controller = controller
        self.subscription_manager = subscription_manager
        self.event_bus = event_bus

        self.cooldown_seconds = max(
            0.0,
            float(cooldown_seconds),
        )

        self.deduplication_seconds = max(
            0.0,
            float(deduplication_seconds),
        )

        self.history_capacity = max(
            50,
            int(history_capacity),
        )

        self._lock = threading.RLock()
        self._armed = bool(armed)
        self._started_at = self._utc_now()

        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._last_execution_monotonic = 0.0
        self._last_command_hash: str | None = None
        self._last_command_monotonic = 0.0

        self._metrics = {
            "received_count": 0,
            "recognized_count": 0,
            "ignored_count": 0,
            "suppressed_count": 0,
            "executed_count": 0,
            "successful_count": 0,
            "failed_count": 0,
            "duplicate_count": 0,
            "cooldown_count": 0,
            "last_received_at": None,
            "last_action": None,
            "last_result": None,
            "last_error": None,
        }

        self._available_methods = self._discover_methods()

        self._subscription_id = (
            self.subscription_manager.subscribe(
                "brain.decision",
                self._consume,
                subscription_id=self.SUBSCRIPTION_ID,
            )
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _json_safe(value: Any) -> Any:
        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            return value

        if isinstance(value, dict):
            return {
                str(key):
                    GeoCoolingControllerCommandBridge
                    ._json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                GeoCoolingControllerCommandBridge
                ._json_safe(item)
                for item in value
            ]

        isoformat = getattr(value, "isoformat", None)

        if callable(isoformat):
            try:
                return isoformat()
            except Exception:
                pass

        return repr(value)

    def _discover_methods(self) -> dict[str, bool]:
        methods = set(self.ACTION_METHODS.values())

        return {
            method: callable(
                getattr(
                    self.controller,
                    method,
                    None,
                )
            )
            for method in sorted(methods)
        }

    @staticmethod
    def _normalize_action(value: Any) -> str:
        if value is None:
            return ""

        normalized = str(value).strip().lower()

        return (
            normalized
            .replace("-", "_")
            .replace(" ", "_")
        )

    def _extract_payload(self, event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("payload", event)

        payload = getattr(event, "payload", None)

        if payload is not None:
            return payload

        return event

    def _extract_action_recursive(
        self,
        value: Any,
        *,
        depth: int = 0,
    ) -> str:
        if depth > 5:
            return ""

        if isinstance(value, str):
            normalized = self._normalize_action(value)

            if (
                normalized in self.ACTION_METHODS
                or normalized in self.IGNORED_ACTIONS
            ):
                return normalized

            return ""

        if isinstance(value, dict):
            priority_keys = (
                "action",
                "command",
                "decision",
                "recommended_action",
                "requested_action",
                "operation",
                "mode",
                "target_state",
                "state",
            )

            for key in priority_keys:
                if key not in value:
                    continue

                candidate = self._extract_action_recursive(
                    value[key],
                    depth=depth + 1,
                )

                if candidate:
                    return candidate

            nested_keys = (
                "payload",
                "result",
                "recommendation",
                "brain",
                "data",
                "details",
            )

            for key in nested_keys:
                if key not in value:
                    continue

                candidate = self._extract_action_recursive(
                    value[key],
                    depth=depth + 1,
                )

                if candidate:
                    return candidate

        if isinstance(value, (list, tuple)):
            for item in value:
                candidate = self._extract_action_recursive(
                    item,
                    depth=depth + 1,
                )

                if candidate:
                    return candidate

        return ""

    def _command_hash(
        self,
        *,
        action: str,
        payload: Any,
    ) -> str:
        raw = json.dumps(
            {
                "action": action,
                "payload": self._json_safe(payload),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        )

        return hashlib.sha256(
            raw.encode("utf-8")
        ).hexdigest()

    def _append_history(
        self,
        entry: dict[str, Any],
    ) -> None:
        with self._lock:
            self._history.append(
                self._json_safe(entry)
            )

    def _publish_result(
        self,
        *,
        action: str,
        result_type: str,
        details: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        try:
            self.event_bus.publish(
                event_type="controller.action",
                source="controller-command-bridge",
                payload={
                    "action": action,
                    "result": result_type,
                    **self._json_safe(details),
                },
                level=level,
            )
        except Exception as exc:
            with self._lock:
                self._metrics["last_error"] = (
                    f"Publication controller.action : {exc!r}"
                )

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        received_at = self._utc_now()
        now_monotonic = time.monotonic()
        payload = self._extract_payload(event)

        action = self._extract_action_recursive(
            payload
        )

        with self._lock:
            self._metrics["received_count"] += 1
            self._metrics["last_received_at"] = (
                received_at
            )
            self._metrics["last_action"] = (
                action or None
            )

        if not action or action in self.IGNORED_ACTIONS:
            with self._lock:
                self._metrics["ignored_count"] += 1
                self._metrics["last_result"] = "ignored"

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "action": action or None,
                    "result": "ignored",
                    "reason":
                        "Aucune commande exécutable",
                }
            )

            return

        method_name = self.ACTION_METHODS.get(action)

        if method_name is None:
            with self._lock:
                self._metrics["ignored_count"] += 1
                self._metrics["last_result"] = (
                    "unsupported"
                )

            return

        with self._lock:
            self._metrics["recognized_count"] += 1

            armed = self._armed

        if not armed:
            with self._lock:
                self._metrics["suppressed_count"] += 1
                self._metrics["last_result"] = (
                    "suppressed_disarmed"
                )

            details = {
                "method": method_name,
                "reason": "Bridge désarmé",
            }

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "action": action,
                    "result": "suppressed",
                    **details,
                }
            )

            self._publish_result(
                action=action,
                result_type="suppressed",
                details=details,
                level="INFO",
            )

            return

        command_hash = self._command_hash(
            action=action,
            payload=payload,
        )

        with self._lock:
            if (
                self._last_command_hash
                == command_hash
                and (
                    now_monotonic
                    - self._last_command_monotonic
                )
                < self.deduplication_seconds
            ):
                self._metrics[
                    "duplicate_count"
                ] += 1

                self._metrics["last_result"] = (
                    "suppressed_duplicate"
                )

                self._append_history(
                    {
                        "received_at": received_at,
                        "event_type": event_type,
                        "action": action,
                        "method": method_name,
                        "result":
                            "suppressed_duplicate",
                    }
                )

                return

            if (
                self._last_execution_monotonic > 0
                and (
                    now_monotonic
                    - self._last_execution_monotonic
                )
                < self.cooldown_seconds
            ):
                self._metrics[
                    "cooldown_count"
                ] += 1

                self._metrics["last_result"] = (
                    "suppressed_cooldown"
                )

                self._append_history(
                    {
                        "received_at": received_at,
                        "event_type": event_type,
                        "action": action,
                        "method": method_name,
                        "result":
                            "suppressed_cooldown",
                    }
                )

                return

            self._last_command_hash = command_hash
            self._last_command_monotonic = (
                now_monotonic
            )

        method = getattr(
            self.controller,
            method_name,
            None,
        )

        if not callable(method):
            error = (
                f"Méthode Controller indisponible : "
                f"{method_name}"
            )

            with self._lock:
                self._metrics["failed_count"] += 1
                self._metrics["last_result"] = "failed"
                self._metrics["last_error"] = error

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "action": action,
                    "method": method_name,
                    "result": "failed",
                    "error": error,
                }
            )

            self._publish_result(
                action=action,
                result_type="failed",
                details={
                    "method": method_name,
                    "error": error,
                },
                level="ERROR",
            )

            return

        with self._lock:
            self._metrics["executed_count"] += 1
            self._last_execution_monotonic = (
                now_monotonic
            )

        try:
            result = method()

            safe_result = self._json_safe(result)

            with self._lock:
                self._metrics[
                    "successful_count"
                ] += 1

                self._metrics["last_result"] = (
                    "executed"
                )

                self._metrics["last_error"] = None

            details = {
                "method": method_name,
                "controller_result": safe_result,
            }

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "action": action,
                    "result": "executed",
                    **details,
                }
            )

            self._publish_result(
                action=action,
                result_type="executed",
                details=details,
                level="INFO",
            )

        except Exception as exc:
            error = repr(exc)

            with self._lock:
                self._metrics["failed_count"] += 1
                self._metrics["last_result"] = "failed"
                self._metrics["last_error"] = error

            details = {
                "method": method_name,
                "error": error,
            }

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "action": action,
                    "result": "failed",
                    **details,
                }
            )

            self._publish_result(
                action=action,
                result_type="failed",
                details=details,
                level="ERROR",
            )

    def arm(self) -> dict[str, Any]:
        with self._lock:
            self._available_methods = (
                self._discover_methods()
            )

            missing = [
                method
                for method, available
                in self._available_methods.items()
                if not available
            ]

            essential_missing = [
                method
                for method in (
                    "request_start",
                    "request_stop",
                    "emergency_stop",
                )
                if method in missing
            ]

            if essential_missing:
                return {
                    "overall": "ERROR",
                    "armed": False,
                    "reason":
                        "Méthodes Controller manquantes",
                    "missing_methods":
                        essential_missing,
                }

            self._armed = True

        return self.status()

    def disarm(self) -> dict[str, Any]:
        with self._lock:
            self._armed = False

        return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "overall": "OK",
                "component":
                    "controller_command_bridge",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "armed": self._armed,
                "safety_mode":
                    "ARMED"
                    if self._armed
                    else "DISARMED",
                "subscription_id":
                    self._subscription_id,
                "started_at":
                    self._started_at,
                "cooldown_seconds":
                    self.cooldown_seconds,
                "deduplication_seconds":
                    self.deduplication_seconds,
                "history_capacity":
                    self.history_capacity,
                "history_size":
                    len(self._history),
                "available_controller_methods":
                    dict(self._available_methods),
                "supported_actions":
                    sorted(
                        self.ACTION_METHODS.keys()
                    ),
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
            min(int(limit), self.history_capacity),
        )

        with self._lock:
            history = list(
                self._history
            )[-normalized_limit:]

        return {
            "overall": "OK",
            "component":
                "controller_command_bridge",
            "limit": normalized_limit,
            "count": len(history),
            "history": history,
        }
