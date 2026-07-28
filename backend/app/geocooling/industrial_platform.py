from __future__ import annotations

import copy
import json
import os
import threading
from collections import Counter, deque
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingEventJournal:
    """Persistent structured event and incident journal."""

    LEVELS = {"DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"}

    def __init__(self, path: str | None = None, capacity: int = 2000) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_EVENT_JOURNAL_PATH", str(base / "industrial-events.jsonl")))
        self.capacity = max(100, int(capacity))
        self._items: deque[dict[str, Any]] = deque(maxlen=self.capacity)
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                for line in self.path.read_text(encoding="utf-8").splitlines()[-self.capacity:]:
                    value = json.loads(line)
                    if isinstance(value, dict):
                        self._items.append(value)
        except Exception:
            self._items.clear()

    def record(self, component: str, event: str, *, level: str = "INFO", message: str = "", details: dict[str, Any] | None = None) -> dict[str, Any]:
        normalized = str(level).upper()
        if normalized not in self.LEVELS:
            raise ValueError(f"Unsupported event level: {normalized}")
        item = {
            "at": utc_now_iso(), "component": str(component), "event": str(event),
            "level": normalized, "message": str(message), "details": details or {},
        }
        with self._lock:
            self._items.append(item)
            try:
                self.path.parent.mkdir(parents=True, exist_ok=True)
                with self.path.open("a", encoding="utf-8") as handle:
                    handle.write(json.dumps(item, ensure_ascii=False) + "\n")
            except Exception:
                pass
        return copy.deepcopy(item)

    def history(self, limit: int = 200, *, minimum_level: str | None = None) -> list[dict[str, Any]]:
        order = {name: index for index, name in enumerate(("DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"))}
        threshold = order.get(str(minimum_level).upper(), 0) if minimum_level else 0
        with self._lock:
            items = [copy.deepcopy(item) for item in self._items if order[item["level"]] >= threshold]
        return items[-max(1, int(limit)):]

    def metrics(self) -> dict[str, Any]:
        items = self.history(self.capacity)
        return {
            "generated_at": utc_now_iso(), "events": len(items),
            "by_level": dict(Counter(item["level"] for item in items)),
            "by_component": dict(Counter(item["component"] for item in items)),
            "incidents": sum(item["level"] in {"ERROR", "CRITICAL"} for item in items),
            "last_incident": next((item for item in reversed(items) if item["level"] in {"ERROR", "CRITICAL"}), None),
        }


class SimulatedHardwareAdapter:
    def __init__(self) -> None:
        self.armed = False
        self.valve_open = False
        self.pump_running = False
        self._last_action_at: str | None = None

    def set_armed(self, armed: bool) -> bool:
        if not armed:
            self.force_safe_state()
        self.armed = bool(armed)
        self._last_action_at = utc_now_iso()
        return self.armed

    def open_valve(self) -> None:
        if not self.armed:
            raise RuntimeError("Hardware adapter is disarmed")
        self.valve_open = True
        self._last_action_at = utc_now_iso()

    def close_valve(self) -> None:
        self.valve_open = False
        self._last_action_at = utc_now_iso()

    def start_pump(self) -> None:
        if not self.armed or not self.valve_open:
            raise RuntimeError("Pump start requires armed adapter and open valve")
        self.pump_running = True
        self._last_action_at = utc_now_iso()

    def stop_pump(self) -> None:
        self.pump_running = False
        self._last_action_at = utc_now_iso()

    def force_safe_state(self) -> None:
        self.pump_running = False
        self.valve_open = False
        self._last_action_at = utc_now_iso()

    def status(self) -> dict[str, Any]:
        return {"driver": "simulation", "simulation": True, "connected": True, "ready": self.armed,
                "armed": self.armed, "valve_open": self.valve_open, "pump_running": self.pump_running,
                "last_action_at": self._last_action_at, "last_error": None}


class GeoCoolingHardwareGateway:
    """Single hardware interface. It always starts disarmed."""

    def __init__(self, physical_factory: Callable[[], Any] | None = None, journal: GeoCoolingEventJournal | None = None) -> None:
        self.mode = os.getenv("GEOCOOLING_HARDWARE_MODE", "simulation").strip().lower()
        self.journal = journal or GeoCoolingEventJournal()
        if self.mode == "waveshare" and physical_factory is not None:
            self.adapter = physical_factory()
        else:
            self.mode = "simulation"
            self.adapter = SimulatedHardwareAdapter()
        self.adapter.set_armed(False)
        self.journal.record("hardware", "gateway_initialized", message=f"mode={self.mode}; disarmed=true")

    def status(self) -> dict[str, Any]:
        data = self.adapter.status()
        data.update({"gateway_mode": self.mode, "safety_policy": "DISARMED_BY_DEFAULT"})
        return data

    def dry_run(self, command: str) -> dict[str, Any]:
        command = str(command).upper()
        allowed = {"OPEN_VALVE", "CLOSE_VALVE", "START_PUMP", "STOP_PUMP", "SAFE_STATE"}
        result = {"generated_at": utc_now_iso(), "command": command, "dry_run": True,
                  "accepted": command in allowed, "hardware_touched": False, "armed": False}
        self.journal.record("hardware", "command_dry_run", level="INFO" if result["accepted"] else "WARNING", details=result)
        return result


class GeoCoolingBrainAdvisorV2:
    """Adds predictive, energy and explainability metadata without driving outputs."""

    VERSION = "BRAIN-V2-1.0"

    def analyze(self, brain_status: dict[str, Any], thermal: dict[str, Any] | None = None) -> dict[str, Any]:
        thermal = thermal or {}
        candidate = brain_status.get("latest") or brain_status.get("current")
        decision = candidate if isinstance(candidate, dict) else brain_status
        predicted = decision.get("predicted_temperature_1h_c")
        indoor = (thermal.get("latest") or {}).get("indoor_temperature_c")
        trend = (thermal.get("trends_c_per_hour") or {}).get("indoor_30m")
        factors = []
        if indoor is not None: factors.append({"factor": "indoor_temperature", "value": indoor})
        if trend is not None: factors.append({"factor": "thermal_trend_c_per_hour", "value": trend})
        if predicted is not None: factors.append({"factor": "predicted_temperature_1h_c", "value": predicted})
        action = decision.get("decision", "WAIT")
        runtime = int(decision.get("recommended_runtime_minutes") or 0)
        optimization = "MINIMIZE_RUNTIME" if runtime > 0 else "HOLD_SAFE_STATE"
        return {"generated_at": utc_now_iso(), "version": self.VERSION, "advisory_only": True,
                "recommended_action": action, "recommended_runtime_minutes": runtime,
                "optimization_strategy": optimization, "confidence": decision.get("confidence"),
                "factors": factors, "explanation": decision.get("explanation") or {"reasons": decision.get("reason", [])}}


class GeoCoolingFieldPreCertification:
    VERSION = "H006-PRE-1.0"

    def evaluate(self, *, hardening: Any, hardware: GeoCoolingHardwareGateway, events: GeoCoolingEventJournal) -> dict[str, Any]:
        startup = hardening.startup_status()
        hardware_status = hardware.status()
        metrics = events.metrics()
        checks = [
            {"name": "startup-self-test", "pass": startup.get("status") == "PASS"},
            {"name": "safe-mode-clear", "pass": not hardening.safe_mode.status().get("active")},
            {"name": "hardware-disarmed", "pass": not hardware_status.get("armed")},
            {"name": "outputs-safe", "pass": not hardware_status.get("pump_running") and not hardware_status.get("valve_open")},
            {"name": "gateway-policy", "pass": hardware_status.get("safety_policy") == "DISARMED_BY_DEFAULT"},
            {"name": "no-critical-incidents", "pass": metrics.get("by_level", {}).get("CRITICAL", 0) == 0},
        ]
        passed = sum(bool(check["pass"]) for check in checks)
        return {"generated_at": utc_now_iso(), "version": self.VERSION,
                "status": "PASS" if passed == len(checks) else "FAIL",
                "score_percent": round(100 * passed / len(checks), 1),
                "field_activation_allowed": False, "requires_physical_waveshare_test": True,
                "checks": checks, "hardware": hardware_status}


class GeoCoolingIndustrialPlatform:
    VERSION = "H003-H006-1.0"

    def __init__(self, *, controller: Any, hardening: Any, physical_factory: Callable[[], Any] | None = None) -> None:
        self.controller = controller
        self.hardening = hardening
        self.events = GeoCoolingEventJournal()
        self.hardware = GeoCoolingHardwareGateway(physical_factory=physical_factory, journal=self.events)
        self.brain_v2 = GeoCoolingBrainAdvisorV2()
        self.pre_certification = GeoCoolingFieldPreCertification()

    def diagnostics(self) -> dict[str, Any]:
        hardening = self.hardening.status()
        hardware = self.hardware.status()
        metrics = self.events.metrics()
        healthy = hardening.get("startup_self_test", {}).get("status") == "PASS" and not hardening.get("safe_mode", {}).get("active")
        return {"generated_at": utc_now_iso(), "version": self.VERSION, "healthy": healthy,
                "mode": "SOFTWARE_READY_HARDWARE_PENDING" if hardware.get("simulation") else "PHYSICAL_GATEWAY_CONFIGURED",
                "hardening": hardening, "hardware": hardware, "events": metrics,
                "home_assistant": {"binary_sensor_healthy": healthy, "binary_sensor_hardware_armed": bool(hardware.get("armed")),
                                   "sensor_incident_count": metrics.get("incidents", 0), "sensor_platform_mode": self.VERSION}}

    def certification(self) -> dict[str, Any]:
        return self.pre_certification.evaluate(hardening=self.hardening, hardware=self.hardware, events=self.events)
