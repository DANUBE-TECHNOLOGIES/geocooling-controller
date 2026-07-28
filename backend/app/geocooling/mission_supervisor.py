from __future__ import annotations

import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingMissionSupervisor:
    """Advisory mission runner. It tracks a Brain V5 plan without driving hardware."""

    VERSION = "H022-MISSION-SUPERVISOR-1.0"

    def __init__(self, brain: Any, path: str | None = None) -> None:
        self.brain = brain
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_MISSION_SUPERVISOR_PATH", str(base / "mission-supervisor.json")))
        self.active: dict[str, Any] | None = None
        self.history: list[dict[str, Any]] = []
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            self.active = data.get("active") if isinstance(data.get("active"), dict) else None
            self.history = data.get("history", [])[-100:] if isinstance(data.get("history"), list) else []
        except Exception:
            return

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps({"active": self.active, "history": self.history[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(), "version": self.VERSION,
            "active_mission": self.active, "mission_count": len(self.history),
            "simulation_only": True, "automatic_execution_allowed": False,
            "physical_activation_allowed": False, "hardware_touched": False,
        }

    def start(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.active is not None:
            raise ValueError("a mission is already active")
        decision = self.brain.decide(payload)
        if decision.get("decision") == "BLOCKED":
            raise ValueError("Brain V5 blocked the mission")
        mission = {
            "mission_id": f"mission-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S%f')}",
            "started_at": utc_now_iso(), "updated_at": utc_now_iso(), "state": "RUNNING_SIMULATION",
            "decision": decision.get("decision"), "planned_runtime_minutes": int((decision.get("timing") or {}).get("recommended_runtime_minutes") or 0),
            "elapsed_minutes": 0, "expected_temperature_c": (decision.get("targets") or {}).get("predicted_final_temperature_c"),
            "last_observed_temperature_c": payload.get("indoor_temperature_c"), "deviation_c": 0.0,
            "stop_reason": None, "software_interlock": False, "plan": decision,
            "simulation_only": True, "physical_activation_allowed": False, "hardware_touched": False,
        }
        self.active = mission
        self._save()
        return mission

    def update(self, payload: dict[str, Any]) -> dict[str, Any]:
        if self.active is None:
            raise ValueError("no active mission")
        try:
            elapsed = max(0, int(payload.get("elapsed_minutes")))
            observed = float(payload.get("observed_temperature_c"))
        except (TypeError, ValueError):
            raise ValueError("elapsed_minutes and observed_temperature_c are required")
        expected = self.active.get("expected_temperature_c")
        deviation = 0.0 if expected is None else observed - float(expected)
        threshold = float(payload.get("maximum_deviation_c", 1.5))
        self.active.update({"updated_at": utc_now_iso(), "elapsed_minutes": elapsed, "last_observed_temperature_c": observed, "deviation_c": round(deviation, 3)})
        if abs(deviation) > threshold:
            self.active.update({"state": "STOPPED_INTERLOCK", "stop_reason": "THERMAL_DEVIATION", "software_interlock": True})
            self._archive_active()
            return self.history[-1]
        if elapsed >= int(self.active.get("planned_runtime_minutes") or 0):
            self.active.update({"state": "COMPLETED", "stop_reason": "PLANNED_RUNTIME_REACHED"})
            self._archive_active()
            return self.history[-1]
        self._save()
        return self.active

    def stop(self, reason: str = "OPERATOR_STOP") -> dict[str, Any]:
        if self.active is None:
            raise ValueError("no active mission")
        self.active.update({"updated_at": utc_now_iso(), "state": "STOPPED", "stop_reason": str(reason)})
        self._archive_active()
        return self.history[-1]

    def _archive_active(self) -> None:
        assert self.active is not None
        self.history.append(self.active)
        self.active = None
        self._save()

    def missions(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.history[-max(1, int(limit)):]
