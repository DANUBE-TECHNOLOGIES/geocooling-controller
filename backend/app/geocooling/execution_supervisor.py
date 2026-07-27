"""
C015.0R1 — GeoCooling Execution Supervisor Core.

Le superviseur écoute les événements ``controller.action`` et construit
un cycle de vie indépendant des commandes physiques.

Événements publiés :
    execution.started
    execution.running
    execution.stopping
    execution.completed
    execution.failed
    execution.reset
    execution.ignored
"""

from __future__ import annotations

import threading
import uuid
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class GeoCoolingExecutionSupervisor:
    """Suit les sessions d'exécution du contrôleur géocooling."""

    PATCH_VERSION = "C015.0R1"
    SUBSCRIPTION_ID = "c0150-execution-supervisor"

    START_ACTIONS = {
        "start",
        "request_start",
        "on",
        "enable",
        "cool",
        "cooling",
        "run",
    }

    STOP_ACTIONS = {
        "stop",
        "request_stop",
        "off",
        "disable",
        "idle",
    }

    EMERGENCY_ACTIONS = {
        "emergency",
        "emergency_stop",
        "force_stop",
        "forced_stop",
        "abort",
    }

    RESET_ACTIONS = {
        "reset",
    }

    SUCCESS_RESULTS = {
        "ok",
        "success",
        "successful",
        "executed",
        "started",
        "running",
        "stopped",
        "completed",
        "done",
        "accepted",
        "true",
    }

    FAILURE_RESULTS = {
        "error",
        "failed",
        "failure",
        "rejected",
        "blocked",
        "denied",
        "exception",
        "false",
    }

    TERMINAL_STATES = {
        "COMPLETED",
        "FAILED",
        "CANCELLED",
    }

    def __init__(
        self,
        *,
        subscription_manager: Any,
        event_bus: Any,
        history_capacity: int = 500,
        event_capacity: int = 1000,
    ) -> None:
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

        self._active_session: dict[str, Any] | None = None

        self._sessions: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.event_capacity
        )

        self._metrics: dict[str, Any] = {
            "received_count": 0,
            "recognized_count": 0,
            "ignored_count": 0,
            "sessions_started": 0,
            "sessions_completed": 0,
            "sessions_failed": 0,
            "sessions_replaced": 0,
            "reset_count": 0,
            "publish_error_count": 0,
            "last_received_at": None,
            "last_action": None,
            "last_state": None,
            "last_session_id": None,
            "last_result": None,
            "last_error": None,
        }

        self._subscription_id = (
            self.subscription_manager.subscribe(
                "controller.action",
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

        return repr(value)

    @staticmethod
    def _extract_payload(event: Any) -> Any:
        if isinstance(event, dict):
            return event.get("payload", event)

        payload = getattr(event, "payload", None)

        if payload is not None:
            return payload

        return event

    def _find_value(
        self,
        value: Any,
        keys: tuple[str, ...],
        *,
        depth: int = 0,
    ) -> Any:
        if depth > 8:
            return None

        if isinstance(value, dict):
            for key in keys:
                if key in value:
                    return value[key]

            preferred_containers = (
                "payload",
                "command",
                "action_data",
                "result",
                "response",
                "details",
                "controller",
                "safety_gate",
                "data",
            )

            for key in preferred_containers:
                if key not in value:
                    continue

                found = self._find_value(
                    value[key],
                    keys,
                    depth=depth + 1,
                )

                if found is not None:
                    return found

            for nested in value.values():
                found = self._find_value(
                    nested,
                    keys,
                    depth=depth + 1,
                )

                if found is not None:
                    return found

        if isinstance(value, (list, tuple)):
            for item in value:
                found = self._find_value(
                    item,
                    keys,
                    depth=depth + 1,
                )

                if found is not None:
                    return found

        return None

    def _extract_action(
        self,
        payload: Any,
    ) -> str:
        if isinstance(payload, str):
            return self._normalize_text(payload)

        raw_action = self._find_value(
            payload,
            (
                "action",
                "command",
                "requested_action",
                "controller_action",
                "operation",
            ),
        )

        return self._normalize_text(raw_action)

    def _extract_result(
        self,
        payload: Any,
    ) -> tuple[str, bool | None]:
        raw_result = self._find_value(
            payload,
            (
                "result",
                "status",
                "outcome",
                "execution_result",
            ),
        )

        success_value = self._find_value(
            payload,
            (
                "success",
                "successful",
                "executed",
                "accepted",
            ),
        )

        if isinstance(success_value, bool):
            return (
                "success" if success_value else "failed",
                success_value,
            )

        normalized = self._normalize_text(raw_result)

        if normalized in self.SUCCESS_RESULTS:
            return normalized, True

        if normalized in self.FAILURE_RESULTS:
            return normalized, False

        error = self._find_value(
            payload,
            (
                "error",
                "exception",
                "last_error",
            ),
        )

        if error:
            return "failed", False

        return normalized or "unknown", None

    def _extract_reason(
        self,
        payload: Any,
    ) -> Any:
        return self._find_value(
            payload,
            (
                "reason",
                "message",
                "description",
                "explanation",
            ),
        )

    def _extract_command_id(
        self,
        payload: Any,
    ) -> Any:
        return self._find_value(
            payload,
            (
                "command_id",
                "decision_id",
                "request_id",
                "correlation_id",
            ),
        )

    def _append_event(
        self,
        *,
        event_type: str,
        action: str,
        state: str,
        session_id: str | None,
        result: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        entry = {
            "timestamp": self._utc_now(),
            "event_type": event_type,
            "session_id": session_id,
            "action": action,
            "state": state,
            "result": result,
            "details": self._json_safe(details or {}),
        }

        self._events.append(entry)

        return entry

    def _publish(
        self,
        *,
        event_type: str,
        payload: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="execution-supervisor",
                payload=self._json_safe(payload),
                level=level,
            )

            self._metrics["last_error"] = None

        except Exception as exc:
            self._metrics[
                "publish_error_count"
            ] += 1

            self._metrics["last_error"] = repr(exc)

    def _session_view(
        self,
        session: dict[str, Any],
    ) -> dict[str, Any]:
        return deepcopy(
            self._json_safe(session)
        )

    def _duration_seconds(
        self,
        session: dict[str, Any],
    ) -> float | None:
        started_at = session.get("started_at")

        if not started_at:
            return None

        ended_at = (
            session.get("ended_at")
            or self._utc_now()
        )

        try:
            start = datetime.fromisoformat(
                str(started_at).replace(
                    "Z",
                    "+00:00",
                )
            )

            end = datetime.fromisoformat(
                str(ended_at).replace(
                    "Z",
                    "+00:00",
                )
            )

            if start.tzinfo is None:
                start = start.replace(
                    tzinfo=timezone.utc
                )

            if end.tzinfo is None:
                end = end.replace(
                    tzinfo=timezone.utc
                )

            return max(
                0.0,
                (end - start).total_seconds(),
            )

        except Exception:
            return None

    def _archive_active_session(
        self,
        *,
        state: str,
        result: str,
        reason: Any,
        source_payload: Any,
    ) -> dict[str, Any] | None:
        session = self._active_session

        if session is None:
            return None

        now = self._utc_now()

        session["state"] = state
        session["result"] = result
        session["ended_at"] = now
        session["updated_at"] = now
        session["reason"] = self._json_safe(reason)
        session["last_payload"] = self._json_safe(
            source_payload
        )
        session["duration_seconds"] = (
            self._duration_seconds(session)
        )

        archived = self._session_view(session)
        self._sessions.append(archived)
        self._active_session = None

        return archived

    def _start_session(
        self,
        *,
        action: str,
        result: str,
        successful: bool | None,
        reason: Any,
        command_id: Any,
        payload: Any,
    ) -> None:
        if self._active_session is not None:
            replaced = self._archive_active_session(
                state="CANCELLED",
                result="replaced_by_new_start",
                reason=(
                    "Nouvelle commande START reçue "
                    "alors qu'une session était active."
                ),
                source_payload=payload,
            )

            self._metrics[
                "sessions_replaced"
            ] += 1

            if replaced is not None:
                self._publish(
                    event_type="execution.failed",
                    payload={
                        "session": replaced,
                        "failure_type":
                            "session_replaced",
                    },
                    level="WARN",
                )

        now = self._utc_now()
        session_id = str(uuid.uuid4())

        state = (
            "FAILED"
            if successful is False
            else "RUNNING"
        )

        session = {
            "session_id": session_id,
            "command_id": command_id,
            "state": state,
            "result": result,
            "created_at": now,
            "started_at": now,
            "running_at": (
                now if state == "RUNNING" else None
            ),
            "stopping_at": None,
            "ended_at": (
                now if state == "FAILED" else None
            ),
            "updated_at": now,
            "duration_seconds": (
                0.0 if state == "FAILED" else None
            ),
            "start_action": action,
            "stop_action": None,
            "reason": self._json_safe(reason),
            "source_payload":
                self._json_safe(payload),
            "last_payload":
                self._json_safe(payload),
            "event_count": 1,
        }

        self._metrics["sessions_started"] += 1
        self._metrics["last_session_id"] = (
            session_id
        )

        self._append_event(
            event_type="execution.started",
            action=action,
            state="STARTING",
            session_id=session_id,
            result=result,
            details={
                "command_id": command_id,
                "successful": successful,
            },
        )

        self._publish(
            event_type="execution.started",
            payload={
                "session": self._session_view(
                    session
                ),
                "phase": "STARTING",
            },
        )

        if successful is False:
            self._sessions.append(
                self._session_view(session)
            )

            self._metrics[
                "sessions_failed"
            ] += 1

            self._metrics["last_state"] = "FAILED"
            self._active_session = None

            self._append_event(
                event_type="execution.failed",
                action=action,
                state="FAILED",
                session_id=session_id,
                result=result,
                details={
                    "reason":
                        self._json_safe(reason),
                },
            )

            self._publish(
                event_type="execution.failed",
                payload={
                    "session":
                        self._session_view(session),
                    "failure_type":
                        "controller_start_failed",
                },
                level="ERROR",
            )

            return

        self._active_session = session
        self._metrics["last_state"] = "RUNNING"

        self._append_event(
            event_type="execution.running",
            action=action,
            state="RUNNING",
            session_id=session_id,
            result=result,
            details={
                "successful": successful,
            },
        )

        self._publish(
            event_type="execution.running",
            payload={
                "session": self._session_view(
                    session
                ),
                "phase": "RUNNING",
            },
        )

    def _stop_session(
        self,
        *,
        action: str,
        result: str,
        successful: bool | None,
        reason: Any,
        payload: Any,
        emergency: bool,
    ) -> None:
        session = self._active_session

        if session is None:
            state = (
                "FAILED"
                if emergency
                or successful is False
                else "COMPLETED"
            )

            self._metrics["last_state"] = state

            self._append_event(
                event_type=(
                    "execution.failed"
                    if state == "FAILED"
                    else "execution.completed"
                ),
                action=action,
                state=state,
                session_id=None,
                result=result,
                details={
                    "orphan_stop": True,
                    "reason":
                        self._json_safe(reason),
                },
            )

            self._publish(
                event_type=(
                    "execution.failed"
                    if state == "FAILED"
                    else "execution.completed"
                ),
                payload={
                    "session": None,
                    "orphan_stop": True,
                    "action": action,
                    "result": result,
                    "reason":
                        self._json_safe(reason),
                },
                level=(
                    "WARN"
                    if state == "FAILED"
                    else "INFO"
                ),
            )

            return

        now = self._utc_now()

        session["state"] = "STOPPING"
        session["stopping_at"] = now
        session["updated_at"] = now
        session["stop_action"] = action
        session["event_count"] = int(
            session.get("event_count", 0)
        ) + 1
        session["last_payload"] = self._json_safe(
            payload
        )

        self._metrics["last_state"] = "STOPPING"

        self._append_event(
            event_type="execution.stopping",
            action=action,
            state="STOPPING",
            session_id=session["session_id"],
            result=result,
            details={
                "emergency": emergency,
                "successful": successful,
            },
        )

        self._publish(
            event_type="execution.stopping",
            payload={
                "session": self._session_view(
                    session
                ),
                "phase": "STOPPING",
                "emergency": emergency,
            },
            level=(
                "WARN" if emergency else "INFO"
            ),
        )

        failed = bool(
            emergency or successful is False
        )

        terminal_state = (
            "FAILED" if failed else "COMPLETED"
        )

        terminal_result = (
            result
            if result != "unknown"
            else (
                "emergency_stop"
                if emergency
                else "completed"
            )
        )

        archived = self._archive_active_session(
            state=terminal_state,
            result=terminal_result,
            reason=reason,
            source_payload=payload,
        )

        self._metrics["last_state"] = (
            terminal_state
        )

        if failed:
            self._metrics[
                "sessions_failed"
            ] += 1
        else:
            self._metrics[
                "sessions_completed"
            ] += 1

        event_type = (
            "execution.failed"
            if failed
            else "execution.completed"
        )

        self._append_event(
            event_type=event_type,
            action=action,
            state=terminal_state,
            session_id=(
                archived.get("session_id")
                if archived
                else None
            ),
            result=terminal_result,
            details={
                "emergency": emergency,
                "reason":
                    self._json_safe(reason),
            },
        )

        self._publish(
            event_type=event_type,
            payload={
                "session": archived,
                "emergency": emergency,
            },
            level=(
                "ERROR" if failed else "INFO"
            ),
        )

    def _reset(
        self,
        *,
        action: str,
        result: str,
        reason: Any,
        payload: Any,
    ) -> None:
        cancelled = None

        if self._active_session is not None:
            cancelled = self._archive_active_session(
                state="CANCELLED",
                result="reset",
                reason=reason or (
                    "Session annulée par RESET."
                ),
                source_payload=payload,
            )

        self._metrics["reset_count"] += 1
        self._metrics["last_state"] = "RESET"

        self._append_event(
            event_type="execution.reset",
            action=action,
            state="RESET",
            session_id=(
                cancelled.get("session_id")
                if cancelled
                else None
            ),
            result=result,
            details={
                "cancelled_session": cancelled,
            },
        )

        self._publish(
            event_type="execution.reset",
            payload={
                "cancelled_session": cancelled,
                "action": action,
                "result": result,
                "reason":
                    self._json_safe(reason),
            },
        )

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        received_at = self._utc_now()
        payload = self._extract_payload(event)

        action = self._extract_action(payload)
        result, successful = self._extract_result(
            payload
        )
        reason = self._extract_reason(payload)
        command_id = self._extract_command_id(
            payload
        )

        with self._lock:
            self._metrics[
                "received_count"
            ] += 1
            self._metrics[
                "last_received_at"
            ] = received_at
            self._metrics["last_action"] = action
            self._metrics["last_result"] = result

            recognized = bool(
                action in self.START_ACTIONS
                or action in self.STOP_ACTIONS
                or action
                in self.EMERGENCY_ACTIONS
                or action in self.RESET_ACTIONS
            )

            if not recognized:
                self._metrics[
                    "ignored_count"
                ] += 1

                self._append_event(
                    event_type="execution.ignored",
                    action=action,
                    state=(
                        self._active_session[
                            "state"
                        ]
                        if self._active_session
                        else "IDLE"
                    ),
                    session_id=(
                        self._active_session[
                            "session_id"
                        ]
                        if self._active_session
                        else None
                    ),
                    result=result,
                    details={
                        "reason":
                            "Action non reconnue",
                        "payload":
                            self._json_safe(payload),
                    },
                )

                return

            self._metrics[
                "recognized_count"
            ] += 1

            if action in self.START_ACTIONS:
                self._start_session(
                    action=action,
                    result=result,
                    successful=successful,
                    reason=reason,
                    command_id=command_id,
                    payload=payload,
                )
                return

            if action in self.STOP_ACTIONS:
                self._stop_session(
                    action=action,
                    result=result,
                    successful=successful,
                    reason=reason,
                    payload=payload,
                    emergency=False,
                )
                return

            if action in self.EMERGENCY_ACTIONS:
                self._stop_session(
                    action=action,
                    result=result,
                    successful=successful,
                    reason=reason,
                    payload=payload,
                    emergency=True,
                )
                return

            self._reset(
                action=action,
                result=result,
                reason=reason,
                payload=payload,
            )

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = (
                self._session_view(
                    self._active_session
                )
                if self._active_session
                else None
            )

            if active is not None:
                active["duration_seconds"] = (
                    self._duration_seconds(active)
                )

            return {
                "overall": "OK",
                "component":
                    "execution_supervisor",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "subscription_id":
                    self._subscription_id,
                "started_at": self._started_at,
                "current_state": (
                    active["state"]
                    if active
                    else "IDLE"
                ),
                "active_session": active,
                "configuration": {
                    "history_capacity":
                        self.history_capacity,
                    "event_capacity":
                        self.event_capacity,
                    "observed_event_type":
                        "controller.action",
                },
                "history_size":
                    len(self._sessions),
                "event_history_size":
                    len(self._events),
                "metrics":
                    dict(self._metrics),
            }

    def current(self) -> dict[str, Any]:
        status = self.status()

        return {
            "overall": status["overall"],
            "component": status["component"],
            "current_state":
                status["current_state"],
            "active_session":
                status["active_session"],
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
            sessions = list(
                self._sessions
            )[-normalized_limit:]

        return {
            "overall": "OK",
            "component":
                "execution_supervisor",
            "limit": normalized_limit,
            "count": len(sessions),
            "sessions": deepcopy(sessions),
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
                "execution_supervisor",
            "limit": normalized_limit,
            "count": len(events),
            "events": deepcopy(events),
        }
