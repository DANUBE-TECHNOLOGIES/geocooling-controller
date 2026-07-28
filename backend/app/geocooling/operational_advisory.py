from __future__ import annotations

import copy
import json
import math
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class GeoCoolingTelemetryHub:
    """Normalizes Home Assistant/field telemetry and feeds Brain V4 learning.

    This component stores observations only. It never writes to hardware.
    """

    VERSION = "H011-TELEMETRY-1.0"
    ALIASES = {
        "indoor_temperature_c": ("indoor_temperature_c", "indoor_temperature", "temperature_interieure"),
        "indoor_humidity_percent": ("indoor_humidity_percent", "humidity_percent", "indoor_humidity"),
        "floor_surface_temperature_c": ("floor_surface_temperature_c", "floor_temperature_c", "surface_temperature_c"),
        "supply_temperature_c": ("supply_temperature_c", "depart_temperature_c", "flow_temperature_c"),
        "return_temperature_c": ("return_temperature_c", "retour_temperature_c"),
        "source_in_temperature_c": ("source_in_temperature_c", "source_in_c"),
        "source_out_temperature_c": ("source_out_temperature_c", "source_out_c"),
        "flow_l_min": ("flow_l_min", "flow_rate_l_min", "debit_l_min"),
        "outdoor_temperature_c": ("outdoor_temperature_c", "outside_temperature_c"),
        "pump_running": ("pump_running", "pump", "circulator_running"),
        "valve_open": ("valve_open", "valve", "electrovalve_open"),
    }

    def __init__(self, brain_v4: Any, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_TELEMETRY_PATH", str(base / "telemetry-h011.json")))
        self.brain_v4 = brain_v4
        self.journal = journal
        self._lock = threading.RLock()
        self._previous: dict[str, Any] | None = None
        self._latest: dict[str, Any] | None = None
        self._last_learning: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._previous = payload.get("previous")
                    self._latest = payload.get("latest")
                    self._last_learning = payload.get("last_learning")
        except Exception:
            self._previous = self._latest = self._last_learning = None

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "previous": self._previous,
                "latest": self._latest,
                "last_learning": self._last_learning,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    @classmethod
    def normalize(cls, payload: dict[str, Any]) -> dict[str, Any]:
        source = payload.get("state") if isinstance(payload.get("state"), dict) else payload
        result: dict[str, Any] = {
            "timestamp": str(payload.get("timestamp") or payload.get("at") or utc_now_iso()),
            "source": str(payload.get("source") or "home-assistant"),
        }
        for canonical, aliases in cls.ALIASES.items():
            value = next((source.get(alias) for alias in aliases if alias in source), None)
            if canonical in {"pump_running", "valve_open"}:
                if value is not None:
                    result[canonical] = bool(value)
            else:
                normalized = _finite(value)
                if normalized is not None:
                    result[canonical] = normalized
        return result

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        observation = self.normalize(payload)
        with self._lock:
            previous = copy.deepcopy(self._latest)
            self._previous = previous
            self._latest = observation
            learning = None
            if previous is not None:
                learning = self.brain_v4.observe(previous, observation)
                self._last_learning = learning
            self._persist()
        self.journal.record("telemetry", "observation_ingested", details={
            "source": observation.get("source"),
            "fields": sorted(key for key in observation if key not in {"timestamp", "source"}),
            "learning_accepted": bool(learning and learning.get("accepted")),
        })
        return {
            "accepted": True,
            "version": self.VERSION,
            "observation": copy.deepcopy(observation),
            "learning": copy.deepcopy(learning),
            "hardware_touched": False,
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "latest": copy.deepcopy(self._latest),
                "previous": copy.deepcopy(self._previous),
                "last_learning": copy.deepcopy(self._last_learning),
                "hardware_touched": False,
            }


class GeoCoolingOperationalAdvisor:
    """Builds a safe, advisory hydraulic execution plan from Brain V4."""

    VERSION = "H011-ADVISOR-1.0"

    def build_plan(self, *, brain: dict[str, Any], safety: dict[str, Any], hardware: dict[str, Any]) -> dict[str, Any]:
        blockers = list(brain.get("blocking_conditions") or [])
        if not safety.get("safe", False):
            blockers.append("safety-manager")
        if hardware.get("armed"):
            blockers.append("unexpected-hardware-armed")

        action = str(brain.get("recommended_action") or "WAIT").upper()
        runtime = int(brain.get("recommended_runtime_minutes") or 0)
        valve_lead = int(brain.get("hydraulic_sequence", {}).get("valve_lead_seconds") or 20)
        pump_overrun = int(brain.get("hydraulic_sequence", {}).get("pump_overrun_seconds") or 30)
        steps: list[dict[str, Any]] = []

        if not blockers and action == "COOL" and runtime > 0:
            steps = [
                {"order": 1, "action": "OPEN_VALVE", "delay_after_seconds": valve_lead},
                {"order": 2, "action": "START_PUMP", "duration_minutes": runtime},
                {"order": 3, "action": "STOP_PUMP", "delay_after_seconds": pump_overrun},
                {"order": 4, "action": "CLOSE_VALVE"},
            ]
        elif action == "STOP":
            steps = [
                {"order": 1, "action": "STOP_PUMP", "delay_after_seconds": pump_overrun},
                {"order": 2, "action": "CLOSE_VALVE"},
            ]

        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "plan_status": "READY_ADVISORY" if steps and not blockers else "BLOCKED_OR_IDLE",
            "recommended_action": action,
            "recommended_runtime_minutes": runtime,
            "steps": steps,
            "blocking_conditions": sorted(set(blockers)),
            "advisory_only": True,
            "physical_command_authorized": False,
            "hardware_touched": False,
            "hardware_remains_disarmed": not bool(hardware.get("armed")),
        }
