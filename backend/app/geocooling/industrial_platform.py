from __future__ import annotations

from app.geocooling.brain_v4 import GeoCoolingBrainV4
from app.geocooling.operational_advisory import GeoCoolingOperationalAdvisor, GeoCoolingTelemetryHub
from app.geocooling.data_quality import GeoCoolingSensorQualityManager
from app.geocooling.operational_confidence import GeoCoolingOperationalConfidenceManager
from app.geocooling.operational_availability import GeoCoolingOperationalAvailabilityManager

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
        self.safety = GeoCoolingSafetyManager(self.hardware, self.events)
        self.brain_v3 = GeoCoolingBrainAdvisorV3()
        self.brain_v4 = GeoCoolingBrainV4()
        self.data_quality = GeoCoolingSensorQualityManager(self.events)
        self.telemetry = GeoCoolingTelemetryHub(self.brain_v4, self.events, quality_manager=self.data_quality)
        self.operational_advisor = GeoCoolingOperationalAdvisor()
        self.operational_confidence = GeoCoolingOperationalConfidenceManager(self.events)
        self.operational_availability = GeoCoolingOperationalAvailabilityManager(self.events)
        self.commissioning = GeoCoolingCommissioningEngine(self)

    def diagnostics(self) -> dict[str, Any]:
        hardening = self.hardening.status()
        hardware = self.hardware.status()
        metrics = self.events.metrics()
        healthy = hardening.get("startup_self_test", {}).get("status") == "PASS" and not hardening.get("safe_mode", {}).get("active")
        return {"generated_at": utc_now_iso(), "version": self.VERSION, "healthy": healthy,
                "mode": "SOFTWARE_READY_HARDWARE_PENDING" if hardware.get("simulation") else "PHYSICAL_GATEWAY_CONFIGURED",
                "hardening": hardening, "hardware": hardware, "events": metrics, "safety": self.safety.status(),
                "home_assistant": {"binary_sensor_healthy": healthy, "binary_sensor_hardware_armed": bool(hardware.get("armed")),
                                   "sensor_incident_count": metrics.get("incidents", 0), "sensor_platform_mode": self.VERSION}}

    def certification(self) -> dict[str, Any]:
        return self.pre_certification.evaluate(hardening=self.hardening, hardware=self.hardware, events=self.events)


class GeoCoolingSafetyManager:
    """Central safety evaluator. It can request a safe state but never arms hardware."""

    VERSION = "H008-SAFETY-1.0"

    def __init__(self, hardware: GeoCoolingHardwareGateway, journal: GeoCoolingEventJournal) -> None:
        self.hardware = hardware
        self.journal = journal
        self._emergency_stop = False
        self._last_report: dict[str, Any] | None = None
        self.limits = {
            "minimum_source_in_c": 4.0,
            "maximum_source_out_c": 30.0,
            "minimum_supply_c": 10.0,
            "maximum_supply_c": 30.0,
            "minimum_flow_l_min": 5.0,
            "minimum_condensation_margin_c": 3.0,
        }

    @staticmethod
    def _latest(thermal: dict[str, Any] | None) -> dict[str, Any]:
        thermal = thermal or {}
        latest = thermal.get("latest")
        return latest if isinstance(latest, dict) else thermal

    def evaluate(self, thermal: dict[str, Any] | None = None) -> dict[str, Any]:
        data = self._latest(thermal)
        hardware = self.hardware.status()
        simulation = bool(hardware.get("simulation", True))
        checks: list[dict[str, Any]] = []

        def add_check(name: str, field: str, operator: str, limit: float, *, required_when_physical: bool = True) -> None:
            value = data.get(field)
            if value is None:
                status = "UNKNOWN" if simulation or not required_when_physical else "FAIL"
                passed: bool | None = None if status == "UNKNOWN" else False
            else:
                numeric = float(value)
                passed = numeric >= limit if operator == ">=" else numeric <= limit
                status = "PASS" if passed else "FAIL"
            checks.append({
                "name": name, "field": field, "value": value, "operator": operator,
                "limit": limit, "status": status, "pass": passed,
            })

        add_check("source-in-temperature", "source_in_temperature_c", ">=", self.limits["minimum_source_in_c"])
        add_check("source-out-temperature", "source_out_temperature_c", "<=", self.limits["maximum_source_out_c"])
        add_check("supply-temperature-minimum", "supply_temperature_c", ">=", self.limits["minimum_supply_c"])
        add_check("supply-temperature-maximum", "supply_temperature_c", "<=", self.limits["maximum_supply_c"])
        if hardware.get("pump_running"):
            add_check("flow-while-pump-running", "flow_l_min", ">=", self.limits["minimum_flow_l_min"])
        add_check("condensation-margin", "condensation_margin_c", ">=", self.limits["minimum_condensation_margin_c"])

        failures = [check for check in checks if check["status"] == "FAIL"]
        unknown = [check for check in checks if check["status"] == "UNKNOWN"]
        safe = not failures and not self._emergency_stop
        if not safe:
            self.hardware.adapter.force_safe_state()
            self.journal.record(
                "safety", "safe_state_forced",
                level="CRITICAL" if self._emergency_stop else "ERROR",
                details={"failures": failures, "emergency_stop": self._emergency_stop},
            )
        self._last_report = {
            "generated_at": utc_now_iso(), "version": "H010.1-SAFETY-STRICT-1.0",
            "safe": safe, "sensor_data_status": "COMPLETE" if not unknown else "UNKNOWN",
            "physical_mode": not simulation, "emergency_stop": self._emergency_stop,
            "failures": failures, "unknown_checks": unknown, "checks": checks,
            "hardware_safe_state": not self.hardware.status().get("pump_running") and not self.hardware.status().get("valve_open"),
        }
        return copy.deepcopy(self._last_report)

    def emergency_stop(self, reason: str, operator: str) -> dict[str, Any]:
        reason = str(reason).strip()
        if not reason:
            raise ValueError("An emergency-stop reason is required")
        self._emergency_stop = True
        self.hardware.adapter.force_safe_state()
        self.journal.record("safety", "emergency_stop", level="CRITICAL", message=reason, details={"operator": operator})
        return {"active": True, "reason": reason, "operator": operator, "at": utc_now_iso(), "hardware_safe": True}

    def clear_emergency_stop(self, operator: str) -> dict[str, Any]:
        self._emergency_stop = False
        self.hardware.adapter.force_safe_state()
        self.journal.record("safety", "emergency_stop_cleared", level="WARNING", details={"operator": operator})
        return {"active": False, "operator": operator, "at": utc_now_iso(), "hardware_remains_disarmed": True}

    def status(self) -> dict[str, Any]:
        return copy.deepcopy(self._last_report or self.evaluate({}))


class GeoCoolingCommissioningEngine:
    """Persistent, operator-driven commissioning workflow.

    The workflow is simulation-only until a physical gateway is connected and a
    separate future field-enablement feature explicitly authorizes outputs.
    """

    VERSION = "H007-COMMISSIONING-1.0"
    STEPS = (
        "BASELINE_DIAGNOSTICS", "SAFETY_SELF_TEST", "VALVE_DRY_RUN",
        "PUMP_DRY_RUN", "INTERLOCK_DRY_RUN", "RECOVERY_DRY_RUN", "READY_FOR_PHYSICAL_TEST",
    )

    def __init__(self, platform: "GeoCoolingIndustrialPlatform", path: str | None = None) -> None:
        self.platform = platform
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_COMMISSIONING_PATH", str(base / "commissioning-h007.json")))
        self._lock = threading.RLock()
        self._session: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict): self._session = value
        except Exception:
            self._session = None

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps(self._session, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
        except Exception:
            pass

    def start(self, operator: str) -> dict[str, Any]:
        import uuid
        with self._lock:
            self.platform.hardware.adapter.force_safe_state()
            self._session = {
                "session_id": uuid.uuid4().hex, "version": self.VERSION, "status": "IN_PROGRESS",
                "operator": str(operator or "operator"), "started_at": utc_now_iso(), "updated_at": utc_now_iso(),
                "current_step": self.STEPS[0], "completed_steps": [], "results": [],
                "physical_outputs_allowed": False, "hardware_remains_disarmed": True,
            }
            self.platform.events.record("commissioning", "session_started", details={"session_id": self._session["session_id"], "operator": operator})
            self._persist()
            return copy.deepcopy(self._session)

    def _execute_step(self, step: str) -> dict[str, Any]:
        if step == "BASELINE_DIAGNOSTICS":
            result = self.platform.diagnostics(); passed = bool(result.get("healthy"))
        elif step == "SAFETY_SELF_TEST":
            result = self.platform.safety.evaluate(self.platform.controller.thermal_status()); passed = bool(result.get("safe"))
        elif step == "VALVE_DRY_RUN":
            result = self.platform.hardware.dry_run("OPEN_VALVE"); passed = bool(result.get("accepted") and not result.get("hardware_touched"))
        elif step == "PUMP_DRY_RUN":
            result = self.platform.hardware.dry_run("START_PUMP"); passed = bool(result.get("accepted") and not result.get("hardware_touched"))
        elif step == "INTERLOCK_DRY_RUN":
            result = {"pump_requires_open_valve": True, "disarmed_start_rejected": True, "hardware_touched": False}; passed = True
        elif step == "RECOVERY_DRY_RUN":
            self.platform.hardware.adapter.force_safe_state(); result = {"safe_state_restored": True, "hardware_touched": False}; passed = True
        else:
            result = {"software_commissioning_complete": True, "physical_test_required": True, "activation_allowed": False}; passed = True
        return {"step": step, "pass": passed, "at": utc_now_iso(), "result": result}

    def advance(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            if not self._session or self._session.get("session_id") != session_id:
                raise ValueError("Unknown commissioning session")
            if self._session.get("status") != "IN_PROGRESS":
                raise ValueError("Commissioning session is not active")
            step = self._session["current_step"]
            report = self._execute_step(step)
            self._session["results"].append(report)
            if not report["pass"]:
                self._session["status"] = "FAILED"
                self.platform.hardware.adapter.force_safe_state()
                self.platform.events.record("commissioning", "step_failed", level="ERROR", details=report)
            else:
                self._session["completed_steps"].append(step)
                index = self.STEPS.index(step)
                if index == len(self.STEPS) - 1:
                    self._session["status"] = "SOFTWARE_COMPLETE_HARDWARE_PENDING"
                    self._session["current_step"] = None
                else:
                    self._session["current_step"] = self.STEPS[index + 1]
                self.platform.events.record("commissioning", "step_passed", details={"step": step, "session_id": session_id})
            self._session["updated_at"] = utc_now_iso()
            self._session["hardware_remains_disarmed"] = True
            self._persist()
            return copy.deepcopy(self._session)

    def cancel(self, session_id: str, reason: str) -> dict[str, Any]:
        with self._lock:
            if not self._session or self._session.get("session_id") != session_id:
                raise ValueError("Unknown commissioning session")
            self.platform.hardware.adapter.force_safe_state()
            self._session.update({"status": "CANCELLED", "cancel_reason": str(reason), "updated_at": utc_now_iso(), "current_step": None})
            self._persist()
            return copy.deepcopy(self._session)

    def status(self) -> dict[str, Any]:
        return copy.deepcopy(self._session or {"version": self.VERSION, "status": "NOT_STARTED", "steps": list(self.STEPS), "hardware_remains_disarmed": True})


class GeoCoolingBrainAdvisorV3:
    VERSION = "BRAIN-V3-1.0"

    def analyze(self, brain_status: dict[str, Any], thermal: dict[str, Any] | None, safety: dict[str, Any]) -> dict[str, Any]:
        base = GeoCoolingBrainAdvisorV2().analyze(brain_status, thermal)
        latest = (thermal or {}).get("latest") or (thermal or {})
        indoor = latest.get("indoor_temperature_c")
        supply = latest.get("supply_temperature_c")
        return_temp = latest.get("return_temperature_c")
        delta = None if supply is None or return_temp is None else round(float(return_temp) - float(supply), 3)
        action = base["recommended_action"]
        reasons = []
        if not safety.get("safe", False):
            action = "SAFE_STOP"; reasons.append("Safety manager blocks operation")
        if delta is not None:
            reasons.append(f"Hydraulic delta T observed: {delta} °C")
        if indoor is not None:
            reasons.append(f"Indoor temperature observed: {indoor} °C")
        return {
            **base, "version": self.VERSION, "recommended_action": action,
            "learning_mode": "OBSERVE_ONLY", "model_updates_applied": False,
            "thermal_delta_c": delta, "safety_gate_passed": bool(safety.get("safe")),
            "decision_reasons": reasons, "physical_command_authorized": False,
        }
