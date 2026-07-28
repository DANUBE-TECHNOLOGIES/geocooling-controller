from __future__ import annotations

import copy
import hashlib
import json
import os
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingOperationalContinuityManager:
    """Validates persisted operational state and plans safe restart recovery.

    This manager is observational only: it never arms or commands hardware.
    """

    VERSION = "H015-OPERATIONAL-CONTINUITY-1.0"
    MAX_RECOVERY_EVENTS = 100

    def __init__(self, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv(
            "GEOCOOLING_OPERATIONAL_CONTINUITY_PATH",
            str(base / "operational-continuity-h015.json"),
        ))
        self.journal = journal
        self._lock = threading.RLock()
        self.session_id = uuid.uuid4().hex
        self.previous_session_id: str | None = None
        self.restart_detected = False
        self.integrity_ok = True
        self.integrity_error: str | None = None
        self._recovery_events: list[dict[str, Any]] = []
        self._last_snapshot: dict[str, Any] | None = None
        self._load()
        self._persist()

    @staticmethod
    def _checksum(payload: dict[str, Any]) -> str:
        canonical = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
        return hashlib.sha256(canonical.encode("utf-8")).hexdigest()

    def _load(self) -> None:
        if not self.path.exists():
            return
        try:
            envelope = json.loads(self.path.read_text(encoding="utf-8"))
            payload = envelope.get("payload")
            checksum = envelope.get("checksum")
            if not isinstance(payload, dict) or checksum != self._checksum(payload):
                raise ValueError("persisted-state-checksum-mismatch")
            self.previous_session_id = payload.get("session_id")
            self.restart_detected = bool(self.previous_session_id)
            if isinstance(payload.get("last_snapshot"), dict):
                self._last_snapshot = payload["last_snapshot"]
            events = payload.get("recovery_events") or []
            self._recovery_events = [item for item in events if isinstance(item, dict)][-self.MAX_RECOVERY_EVENTS:]
        except Exception as exc:
            self.integrity_ok = False
            self.integrity_error = str(exc)
            self.restart_detected = True
            self._last_snapshot = None
            self._recovery_events = []

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "session_id": self.session_id,
                "updated_at": utc_now_iso(),
                "last_snapshot": self._last_snapshot,
                "recovery_events": self._recovery_events[-self.MAX_RECOVERY_EVENTS:],
            }
            envelope = {"payload": payload, "checksum": self._checksum(payload)}
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps(envelope, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception as exc:
            self.integrity_ok = False
            self.integrity_error = f"persist-failed:{exc}"

    def evaluate(
        self,
        *,
        availability: dict[str, Any],
        confidence: dict[str, Any],
        safety: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            current_snapshot = {
                "availability": availability.get("availability"),
                "availability_score": availability.get("availability_score"),
                "confidence_level": confidence.get("confidence_level"),
                "confidence_score": confidence.get("confidence_score"),
                "safe": bool(safety.get("safe", False)),
                "emergency_stop": bool(safety.get("emergency_stop", False)),
                "hardware_armed": bool(hardware.get("armed", False)),
                "pump_running": bool(hardware.get("pump_running", False)),
                "valve_open": bool(hardware.get("valve_open", False)),
                "captured_at": utc_now_iso(),
            }

            inconsistencies: list[str] = []
            if current_snapshot["hardware_armed"]:
                inconsistencies.append("hardware-armed-at-continuity-check")
            if current_snapshot["pump_running"] or current_snapshot["valve_open"]:
                inconsistencies.append("outputs-not-in-safe-state")
            if not current_snapshot["safe"]:
                inconsistencies.append("safety-not-clear")
            if not self.integrity_ok:
                inconsistencies.append("persisted-state-integrity-failed")

            recovery_required = bool(
                self.restart_detected
                or inconsistencies
                or availability.get("recovery_required")
            )
            recovery_steps: list[str] = []
            if self.restart_detected:
                recovery_steps.append("validate-post-restart-baseline")
            if not self.integrity_ok:
                recovery_steps.append("rebuild-persisted-operational-state")
            if current_snapshot["hardware_armed"] or current_snapshot["pump_running"] or current_snapshot["valve_open"]:
                recovery_steps.append("confirm-hardware-safe-state")
            if not current_snapshot["safe"]:
                recovery_steps.append("resolve-safety-blocking-condition")
            if availability.get("recovery_required"):
                recovery_steps.extend(availability.get("recovery_steps") or [])
            if recovery_required:
                recovery_steps.append("collect-stable-observations")

            continuity_state = "READY"
            if inconsistencies:
                continuity_state = "BLOCKED"
            elif recovery_required:
                continuity_state = "RECOVERY_REQUIRED"

            report = {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "session_id": self.session_id,
                "previous_session_id": self.previous_session_id,
                "restart_detected": self.restart_detected,
                "persisted_state_integrity": "PASS" if self.integrity_ok else "FAIL",
                "integrity_error": self.integrity_error,
                "continuity_state": continuity_state,
                "inconsistencies": inconsistencies,
                "recovery_required": recovery_required,
                "recovery_steps": list(dict.fromkeys(recovery_steps)),
                "current_snapshot": current_snapshot,
                "previous_snapshot": copy.deepcopy(self._last_snapshot),
                "automatic_mode_allowed": bool(
                    continuity_state == "READY"
                    and availability.get("automatic_mode_allowed")
                    and confidence.get("automatic_mode_allowed")
                    and not hardware.get("armed")
                ),
                "software_interlock_required": continuity_state != "READY",
                "hardware_remains_disarmed": not bool(hardware.get("armed")),
                "physical_activation_allowed": False,
                "hardware_touched": False,
                "home_assistant": {
                    "sensor_continuity_state": continuity_state,
                    "binary_sensor_restart_detected": self.restart_detected,
                    "binary_sensor_state_integrity_ok": self.integrity_ok,
                    "binary_sensor_recovery_required": recovery_required,
                    "sensor_continuity_inconsistency_count": len(inconsistencies),
                },
            }
            self._last_snapshot = current_snapshot
            event = {
                "at": report["generated_at"],
                "state": continuity_state,
                "restart_detected": self.restart_detected,
                "inconsistencies": inconsistencies,
            }
            self._recovery_events.append(event)
            self._recovery_events = self._recovery_events[-self.MAX_RECOVERY_EVENTS:]
            self._persist()

        if inconsistencies:
            self.journal.record(
                "operational_continuity",
                "continuity_blocked",
                level="ERROR",
                details={"inconsistencies": inconsistencies},
            )
        elif self.restart_detected:
            self.journal.record(
                "operational_continuity",
                "restart_recovery_required",
                level="WARNING",
                details={"previous_session_id": self.previous_session_id},
            )
        return copy.deepcopy(report)

    def history(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            items = copy.deepcopy(self._recovery_events[-limit:])
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "items": items,
            "count": len(items),
            "hardware_touched": False,
        }
