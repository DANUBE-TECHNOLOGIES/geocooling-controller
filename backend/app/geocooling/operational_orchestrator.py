from __future__ import annotations

import copy
import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingOperationalOrchestrator:
    """Computes the global operational state without commanding hardware."""

    VERSION = "H016-OPERATIONAL-ORCHESTRATION-1.0"
    MAX_HISTORY = 100

    def __init__(self, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv(
            "GEOCOOLING_OPERATIONAL_ORCHESTRATOR_PATH",
            str(base / "operational-orchestrator-h016.json"),
        ))
        self.journal = journal
        self._lock = threading.RLock()
        self.maintenance_active = False
        self.maintenance_reason: str | None = None
        self.maintenance_operator: str | None = None
        self.maintenance_since: str | None = None
        self._history: list[dict[str, Any]] = []
        self._last_state: str | None = None
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.maintenance_active = bool(data.get("maintenance_active", False))
            self.maintenance_reason = data.get("maintenance_reason")
            self.maintenance_operator = data.get("maintenance_operator")
            self.maintenance_since = data.get("maintenance_since")
            self._last_state = data.get("last_state")
            history = data.get("history") or []
            self._history = [item for item in history if isinstance(item, dict)][-self.MAX_HISTORY:]
        except Exception:
            self.maintenance_active = True
            self.maintenance_reason = "persisted-orchestrator-state-unreadable"
            self.maintenance_operator = "system"
            self.maintenance_since = utc_now_iso()

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "maintenance_active": self.maintenance_active,
            "maintenance_reason": self.maintenance_reason,
            "maintenance_operator": self.maintenance_operator,
            "maintenance_since": self.maintenance_since,
            "last_state": self._last_state,
            "history": self._history[-self.MAX_HISTORY:],
            "updated_at": utc_now_iso(),
        }
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
        tmp.replace(self.path)

    def set_maintenance(self, active: bool, *, operator: str, reason: str) -> dict[str, Any]:
        operator = str(operator or "unknown").strip()
        reason = str(reason or "maintenance operation").strip()
        with self._lock:
            self.maintenance_active = bool(active)
            self.maintenance_operator = operator if active else None
            self.maintenance_reason = reason if active else None
            self.maintenance_since = utc_now_iso() if active else None
            self._persist()
        self.journal.record(
            "operational_orchestrator",
            "maintenance_enabled" if active else "maintenance_disabled",
            level="WARNING" if active else "INFO",
            details={"operator": operator, "reason": reason},
        )
        return self.maintenance_status()

    def maintenance_status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "active": self.maintenance_active,
                "reason": self.maintenance_reason,
                "operator": self.maintenance_operator,
                "since": self.maintenance_since,
            }

    def evaluate(
        self,
        *,
        continuity: dict[str, Any],
        availability: dict[str, Any],
        confidence: dict[str, Any],
        safety: dict[str, Any],
        hardware: dict[str, Any],
    ) -> dict[str, Any]:
        with self._lock:
            reasons: list[str] = []
            safe = bool(safety.get("safe", False)) and not bool(safety.get("emergency_stop", False))
            hardware_safe = not bool(hardware.get("armed")) and not bool(hardware.get("pump_running")) and not bool(hardware.get("valve_open"))

            if self.maintenance_active:
                state = "MAINTENANCE"
                reasons.append(self.maintenance_reason or "maintenance-active")
            elif not safe or continuity.get("continuity_state") == "BLOCKED" or not hardware_safe:
                state = "BLOCKED"
                if not safe:
                    reasons.append("safety-not-clear")
                if continuity.get("continuity_state") == "BLOCKED":
                    reasons.append("continuity-blocked")
                if not hardware_safe:
                    reasons.append("hardware-not-in-safe-state")
            elif continuity.get("recovery_required") or availability.get("recovery_required"):
                state = "RECOVERY"
                reasons.append("controlled-recovery-required")
            elif availability.get("availability") == "AVAILABLE" and confidence.get("confidence_level") == "HIGH":
                state = "NORMAL"
            else:
                state = "DEGRADED"
                if availability.get("availability") != "AVAILABLE":
                    reasons.append("availability-not-nominal")
                if confidence.get("confidence_level") != "HIGH":
                    reasons.append("confidence-not-high")

            automatic_mode_allowed = bool(
                state == "NORMAL"
                and continuity.get("automatic_mode_allowed")
                and availability.get("automatic_mode_allowed")
                and confidence.get("automatic_mode_allowed")
                and safe
                and hardware_safe
            )
            transition = self._last_state is not None and self._last_state != state
            if transition:
                self.journal.record(
                    "operational_orchestrator",
                    "state_transition",
                    level="WARNING" if state != "NORMAL" else "INFO",
                    details={"from": self._last_state, "to": state, "reasons": reasons},
                )
            self._last_state = state
            item = {"at": utc_now_iso(), "state": state, "reasons": reasons}
            self._history.append(item)
            self._history = self._history[-self.MAX_HISTORY:]
            self._persist()

            return {
                "generated_at": item["at"],
                "version": self.VERSION,
                "operational_state": state,
                "state_reasons": reasons,
                "maintenance": self.maintenance_status(),
                "transition_detected": transition,
                "automatic_mode_allowed": automatic_mode_allowed,
                "software_interlock_required": state != "NORMAL",
                "recovery_authorized": state == "RECOVERY" and safe and hardware_safe,
                "return_to_normal_conditions": [
                    "safety-clear",
                    "hardware-safe-state",
                    "continuity-ready",
                    "availability-available",
                    "confidence-high",
                    "maintenance-disabled",
                ],
                "physical_activation_allowed": False,
                "hardware_remains_disarmed": not bool(hardware.get("armed")),
                "hardware_touched": False,
                "home_assistant": {
                    "sensor_operational_state": state,
                    "binary_sensor_maintenance_active": self.maintenance_active,
                    "binary_sensor_software_interlock": state != "NORMAL",
                    "binary_sensor_recovery_authorized": state == "RECOVERY" and safe and hardware_safe,
                },
            }

    def history(self, limit: int = 20) -> dict[str, Any]:
        limit = max(1, min(100, int(limit)))
        with self._lock:
            items = copy.deepcopy(self._history[-limit:])
        return {"generated_at": utc_now_iso(), "version": self.VERSION, "items": items, "count": len(items), "hardware_touched": False}
