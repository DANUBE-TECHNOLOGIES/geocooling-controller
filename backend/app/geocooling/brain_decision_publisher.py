"""
C014.1R2 — Normalisation des décisions du GeoCoolingBrain.

Entrée :
    brain.decision

Sortie :
    brain.command
"""

from __future__ import annotations

import hashlib
import json
import threading
import time
import uuid
from collections import deque
from datetime import datetime, timezone
from typing import Any


class GeoCoolingBrainDecisionPublisher:
    """Transforme les décisions métier en commandes normalisées."""

    PATCH_VERSION = "C014.1R2"
    SUBSCRIPTION_ID = "c0141-brain-decision-publisher"

    ACTION_MAP = {
        "start": "start",
        "on": "start",
        "enable": "start",
        "cool": "start",
        "cooling": "start",
        "run": "start",
        "activate": "start",
        "request_start": "start",

        "stop": "stop",
        "off": "stop",
        "disable": "stop",
        "idle": "stop",
        "request_stop": "stop",

        "force_stop": "emergency_stop",
        "forced_stop": "emergency_stop",
        "emergency": "emergency_stop",
        "emergency_stop": "emergency_stop",
        "abort": "emergency_stop",

        "reset": "reset",

        "wait": "wait",
        "hold": "wait",
        "maintain": "wait",
        "observe": "wait",
        "monitor": "wait",
        "noop": "wait",
        "no_op": "wait",
        "none": "wait",
    }

    def __init__(
        self,
        *,
        subscription_manager: Any,
        event_bus: Any,
        deduplication_seconds: float = 2.0,
        history_capacity: int = 500,
    ) -> None:
        self.subscription_manager = subscription_manager
        self.event_bus = event_bus

        self.deduplication_seconds = max(
            0.0,
            float(deduplication_seconds),
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

        self._last_hash: str | None = None
        self._last_hash_monotonic = 0.0

        self._metrics = {
            "received_count": 0,
            "normalized_count": 0,
            "published_count": 0,
            "ignored_count": 0,
            "duplicate_count": 0,
            "error_count": 0,
            "last_received_at": None,
            "last_published_at": None,
            "last_raw_decision": None,
            "last_action": None,
            "last_error": None,
        }

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
        if depth > 6:
            return None

        if isinstance(value, dict):
            for key in keys:
                if key in value:
                    return value[key]

            for nested_key in (
                "payload",
                "brain",
                "decision_data",
                "result",
                "data",
                "details",
                "recommendation",
            ):
                if nested_key not in value:
                    continue

                found = self._find_value(
                    value[nested_key],
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

    def _extract_raw_decision(self, payload: Any) -> Any:
        if isinstance(payload, str):
            return payload

        return self._find_value(
            payload,
            (
                "decision",
                "action",
                "command",
                "recommended_action",
                "requested_action",
                "operation",
                "target_state",
            ),
        )

    def _extract_number(
        self,
        payload: Any,
        keys: tuple[str, ...],
    ) -> float | int | None:
        value = self._find_value(
            payload,
            keys,
        )

        if isinstance(value, bool):
            return None

        if isinstance(value, (int, float)):
            return value

        try:
            if value is not None:
                return float(value)
        except (TypeError, ValueError):
            pass

        return None

    def _command_hash(
        self,
        command: dict[str, Any],
    ) -> str:
        raw = json.dumps(
            command,
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

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        received_at = self._utc_now()
        now_monotonic = time.monotonic()
        payload = self._extract_payload(event)

        raw_decision = self._extract_raw_decision(
            payload
        )

        normalized_decision = self._normalize_text(
            raw_decision
        )

        action = self.ACTION_MAP.get(
            normalized_decision
        )

        with self._lock:
            self._metrics["received_count"] += 1
            self._metrics["last_received_at"] = (
                received_at
            )
            self._metrics["last_raw_decision"] = (
                raw_decision
            )
            self._metrics["last_action"] = action

        if action is None:
            with self._lock:
                self._metrics["ignored_count"] += 1

            self._append_history(
                {
                    "received_at": received_at,
                    "event_type": event_type,
                    "raw_decision": raw_decision,
                    "result": "ignored",
                    "reason":
                        "Décision non reconnue",
                }
            )

            return

        confidence = self._extract_number(
            payload,
            ("confidence",),
        )

        data_quality = self._extract_number(
            payload,
            ("data_quality", "quality"),
        )

        cooling_score = self._extract_number(
            payload,
            ("cooling_score",),
        )

        risk_score = self._extract_number(
            payload,
            ("risk_score",),
        )

        total_score = self._extract_number(
            payload,
            ("total_score", "score"),
        )

        runtime_minutes = self._extract_number(
            payload,
            (
                "recommended_runtime_minutes",
                "runtime_minutes",
            ),
        )

        operating_mode = self._find_value(
            payload,
            (
                "operating_mode",
                "mode",
            ),
        )

        reason = self._find_value(
            payload,
            (
                "reason",
                "reasons",
                "explanation",
            ),
        )

        generated_at = self._find_value(
            payload,
            (
                "generated_at",
                "timestamp",
            ),
        )

        command = {
            "command_id": str(uuid.uuid4()),
            "action": action,
            "raw_decision": raw_decision,
            "confidence": confidence,
            "data_quality": data_quality,
            "cooling_score": cooling_score,
            "risk_score": risk_score,
            "total_score": total_score,
            "recommended_runtime_minutes":
                runtime_minutes,
            "operating_mode": operating_mode,
            "reason": self._json_safe(reason),
            "brain_generated_at": generated_at,
            "normalized_at": received_at,
            "source_event_type": event_type,
            "source_payload":
                self._json_safe(payload),
        }

        deduplication_view = {
            key: value
            for key, value in command.items()
            if key not in (
                "command_id",
                "normalized_at",
            )
        }

        command_hash = self._command_hash(
            deduplication_view
        )

        with self._lock:
            if (
                self._last_hash == command_hash
                and (
                    now_monotonic
                    - self._last_hash_monotonic
                )
                < self.deduplication_seconds
            ):
                self._metrics[
                    "duplicate_count"
                ] += 1

                self._append_history(
                    {
                        "received_at": received_at,
                        "raw_decision": raw_decision,
                        "action": action,
                        "result":
                            "suppressed_duplicate",
                    }
                )

                return

            self._last_hash = command_hash
            self._last_hash_monotonic = (
                now_monotonic
            )
            self._metrics["normalized_count"] += 1

        try:
            self.event_bus.publish(
                event_type="brain.command",
                source="brain-decision-publisher",
                payload=command,
                level="INFO",
            )

            with self._lock:
                self._metrics["published_count"] += 1
                self._metrics["last_published_at"] = (
                    self._utc_now()
                )
                self._metrics["last_error"] = None

            self._append_history(
                {
                    "received_at": received_at,
                    "raw_decision": raw_decision,
                    "action": action,
                    "command_id":
                        command["command_id"],
                    "result": "published",
                }
            )

        except Exception as exc:
            with self._lock:
                self._metrics["error_count"] += 1
                self._metrics["last_error"] = repr(
                    exc
                )

            self._append_history(
                {
                    "received_at": received_at,
                    "raw_decision": raw_decision,
                    "action": action,
                    "result": "error",
                    "error": repr(exc),
                }
            )

            raise

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "overall": "OK",
                "component":
                    "brain_decision_publisher",
                "patch_version":
                    self.PATCH_VERSION,
                "running": True,
                "subscription_id":
                    self._subscription_id,
                "started_at": self._started_at,
                "deduplication_seconds":
                    self.deduplication_seconds,
                "history_capacity":
                    self.history_capacity,
                "history_size":
                    len(self._history),
                "supported_decisions":
                    sorted(self.ACTION_MAP.keys()),
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
                "brain_decision_publisher",
            "limit": normalized_limit,
            "count": len(history),
            "history": history,
        }
