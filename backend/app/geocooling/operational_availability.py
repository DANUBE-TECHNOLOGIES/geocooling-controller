from __future__ import annotations

import copy
import json
import os
import threading
from collections import deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingOperationalAvailabilityManager:
    """Tracks persistent operational anomalies and computes availability.

    The manager is observational only. It may recommend an interlock or
    controlled recovery, but it never commands or arms hardware.
    """

    VERSION = "H014-OPERATIONAL-AVAILABILITY-1.0"
    MAX_HISTORY = 120
    PERSISTENCE_THRESHOLD = 3

    def __init__(self, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv(
            "GEOCOOLING_OPERATIONAL_AVAILABILITY_PATH",
            str(base / "operational-availability-h014.json"),
        ))
        self.journal = journal
        self._lock = threading.RLock()
        self._history: deque[dict[str, Any]] = deque(maxlen=self.MAX_HISTORY)
        self._last_report: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                for item in payload.get("history", [])[-self.MAX_HISTORY:]:
                    if isinstance(item, dict):
                        self._history.append(item)
                if isinstance(payload.get("last_report"), dict):
                    self._last_report = payload["last_report"]
        except Exception:
            self._history.clear()
            self._last_report = None

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "history": list(self._history),
                "last_report": self._last_report,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    @staticmethod
    def _conditions(confidence: dict[str, Any], quality: dict[str, Any], safety: dict[str, Any]) -> list[str]:
        conditions = list(confidence.get("blocking_conditions") or [])
        if str(quality.get("status") or "NOT_EVALUATED") == "FAIL":
            conditions.append("data-quality-failed")
        if safety.get("emergency_stop"):
            conditions.append("emergency-stop")
        if not safety.get("safe", False):
            conditions.append("safety-failed")
        return sorted(set(str(item) for item in conditions if item))

    def evaluate(
        self,
        *,
        confidence: dict[str, Any],
        quality: dict[str, Any],
        safety: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        conditions = self._conditions(confidence, quality, safety)
        observation = {
            "at": utc_now_iso(),
            "conditions": conditions,
            "confidence_score": int(confidence.get("confidence_score") or 0),
            "quality_status": str(quality.get("status") or "NOT_EVALUATED"),
            "safe": bool(safety.get("safe", False)),
        }

        with self._lock:
            self._history.append(observation)
            window = list(self._history)[-self.PERSISTENCE_THRESHOLD:]
            persistence: dict[str, int] = {}
            for item in window:
                for condition in item.get("conditions", []):
                    persistence[condition] = persistence.get(condition, 0) + 1
            persistent = sorted(
                condition for condition, count in persistence.items()
                if count >= self.PERSISTENCE_THRESHOLD
            )

            confidence_score = int(confidence.get("confidence_score") or 0)
            availability_score = confidence_score
            if conditions:
                availability_score -= min(35, 8 * len(conditions))
            if persistent:
                availability_score -= min(35, 12 * len(persistent))
            if safety.get("emergency_stop"):
                availability_score = 0
            availability_score = max(0, min(100, availability_score))

            if availability_score >= 90 and not conditions:
                availability = "AVAILABLE"
            elif availability_score >= 65 and not persistent:
                availability = "DEGRADED"
            else:
                availability = "UNAVAILABLE"

            recovery_required = bool(persistent or safety.get("emergency_stop"))
            recovery_steps = []
            if "stale-telemetry" in conditions:
                recovery_steps.append("restore-fresh-telemetry")
            if "required-sensors-missing" in conditions:
                recovery_steps.append("restore-required-sensors")
            if "sensor-drift-detected" in conditions:
                recovery_steps.append("inspect-and-calibrate-sensors")
            if "data-quality-failed" in conditions:
                recovery_steps.append("resolve-data-quality-failures")
            if safety.get("emergency_stop"):
                recovery_steps.append("operator-clear-emergency-stop")
            if persistent:
                recovery_steps.append("validate-stable-observations")

            report = {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "availability_score": availability_score,
                "availability": availability,
                "active_conditions": conditions,
                "persistent_conditions": persistent,
                "persistence_threshold": self.PERSISTENCE_THRESHOLD,
                "recovery_required": recovery_required,
                "recovery_steps": list(dict.fromkeys(recovery_steps)),
                "automatic_mode_allowed": bool(
                    availability == "AVAILABLE"
                    and confidence.get("automatic_mode_allowed")
                    and not hardware.get("armed")
                ),
                "software_interlock_required": availability != "AVAILABLE",
                "hardware_remains_disarmed": not bool(hardware.get("armed")),
                "physical_activation_allowed": False,
                "hardware_touched": False,
                "home_assistant": {
                    "sensor_availability_score": availability_score,
                    "sensor_availability_state": availability,
                    "binary_sensor_recovery_required": recovery_required,
                    "sensor_persistent_condition_count": len(persistent),
                },
            }
            previous = self._last_report
            self._last_report = report
            self._persist()

        if persistent and (not previous or previous.get("persistent_conditions") != persistent):
            self.journal.record(
                "operational_availability",
                "persistent_anomaly_detected",
                level="ERROR",
                details={"persistent_conditions": persistent, "availability_score": availability_score},
            )
        return copy.deepcopy(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._last_report or {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "availability_score": 0,
                "availability": "UNKNOWN",
                "active_conditions": [],
                "persistent_conditions": [],
                "recovery_required": True,
                "automatic_mode_allowed": False,
                "software_interlock_required": True,
                "hardware_remains_disarmed": True,
                "physical_activation_allowed": False,
                "hardware_touched": False,
            })

    def history(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            return {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "items": copy.deepcopy(list(self._history)[-limit:]),
                "count": min(limit, len(self._history)),
                "hardware_touched": False,
            }
