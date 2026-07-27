"""
GeoCooling Release 0.7.0 — Water Test Framework.

Gestion persistante de sessions d'essai entièrement simulées.
Aucune commande physique n'est autorisée dans cette release.
"""

from __future__ import annotations

import json
import os
import threading
import uuid
from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class WaterTestError(RuntimeError):
    pass


class GeoCoolingWaterTestFramework:
    VERSION = "0.7.0"

    STATUSES = {
        "CREATED",
        "READY",
        "RUNNING",
        "PAUSED",
        "FINISHED",
        "FAILED",
        "ABORTED",
    }

    TERMINAL_STATUSES = {"FINISHED", "FAILED", "ABORTED"}

    SCENARIOS = {
        "manual_valve_simulation": {
            "name": "Manual Valve Simulation",
            "description": "Simulation d'ouverture et de fermeture de l'EV.",
            "physical_execution": False,
            "steps": [
                {"id": "baseline", "action": "CAPTURE_TWIN"},
                {"id": "open", "action": "SIMULATE_VALVE_OPEN"},
                {"id": "observe", "action": "CAPTURE_TWIN"},
                {"id": "close", "action": "SIMULATE_VALVE_CLOSED"},
            ],
        },
        "manual_pump_simulation": {
            "name": "Manual Pump Simulation",
            "description": "Simulation de démarrage et d'arrêt du circulateur.",
            "physical_execution": False,
            "steps": [
                {"id": "baseline", "action": "CAPTURE_TWIN"},
                {"id": "start", "action": "SIMULATE_PUMP_ON"},
                {"id": "observe", "action": "CAPTURE_TWIN"},
                {"id": "stop", "action": "SIMULATE_PUMP_OFF"},
            ],
        },
        "complete_hydraulic_simulation": {
            "name": "Complete Hydraulic Simulation",
            "description": "Simulation complète EV, débit, pompe et ΔT.",
            "physical_execution": False,
            "steps": [
                {"id": "baseline", "action": "CAPTURE_TWIN"},
                {"id": "valve", "action": "SIMULATE_VALVE_OPEN"},
                {"id": "flow", "action": "SIMULATE_FLOW"},
                {"id": "pump", "action": "SIMULATE_PUMP_ON"},
                {"id": "thermal", "action": "SIMULATE_THERMAL"},
                {"id": "shutdown", "action": "SIMULATE_SHUTDOWN"},
            ],
        },
        "delta_t_simulation": {
            "name": "DeltaT Simulation",
            "description": "Simulation et enregistrement d'un différentiel thermique.",
            "physical_execution": False,
            "steps": [
                {"id": "baseline", "action": "CAPTURE_TWIN"},
                {"id": "thermal", "action": "SIMULATE_THERMAL"},
                {"id": "report", "action": "GENERATE_REPORT"},
            ],
        },
        "emergency_stop_simulation": {
            "name": "Emergency Stop Simulation",
            "description": "Validation logique d'un arrêt sans action matérielle.",
            "physical_execution": False,
            "steps": [
                {"id": "running", "action": "SIMULATE_RUNNING"},
                {"id": "abort", "action": "SIMULATE_ABORT"},
                {"id": "safe_state", "action": "CAPTURE_TWIN"},
            ],
        },
    }

    def __init__(
        self,
        *,
        controller: Any,
        digital_twin: Any,
        event_bus: Any = None,
        storage_path: str | None = None,
    ) -> None:
        self.controller = controller
        self.digital_twin = digital_twin
        self.event_bus = event_bus
        self.storage_path = Path(
            storage_path
            or os.getenv(
                "GEOCOOLING_WATER_TEST_STORAGE",
                "/app/data/geocooling/water_test_sessions.json",
            )
        )
        self._lock = threading.RLock()
        self._sessions: dict[str, dict[str, Any]] = {}
        self._active_session_id: str | None = None
        self._started_at = self._utc_now()
        self._load()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _safe(value: Any) -> Any:
        if value is None or isinstance(value, (bool, int, float, str)):
            return value
        if isinstance(value, dict):
            return {
                str(key): GeoCoolingWaterTestFramework._safe(item)
                for key, item in value.items()
            }
        if isinstance(value, (list, tuple, set)):
            return [
                GeoCoolingWaterTestFramework._safe(item)
                for item in value
            ]
        enum_value = getattr(value, "value", None)
        if isinstance(enum_value, (bool, int, float, str)):
            return enum_value
        return repr(value)

    def _load(self) -> None:
        with self._lock:
            if not self.storage_path.exists():
                return
            try:
                data = json.loads(
                    self.storage_path.read_text(encoding="utf-8")
                )
            except Exception:
                return
            sessions = data.get("sessions", {})
            if isinstance(sessions, dict):
                self._sessions = sessions
            active = data.get("active_session_id")
            if active in self._sessions:
                status = self._sessions[active].get("status")
                if status not in self.TERMINAL_STATUSES:
                    self._active_session_id = active

    def _persist(self) -> None:
        self.storage_path.parent.mkdir(parents=True, exist_ok=True)
        payload = {
            "version": self.VERSION,
            "updated_at": self._utc_now(),
            "active_session_id": self._active_session_id,
            "sessions": self._sessions,
        }
        temporary = self.storage_path.with_suffix(".tmp")
        temporary.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
        os.replace(temporary, self.storage_path)

    def _publish(
        self,
        event_type: str,
        session: dict[str, Any],
        level: str = "INFO",
    ) -> None:
        if self.event_bus is None:
            return
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="water-test-framework",
                payload=self._safe(session),
                level=level,
            )
        except Exception:
            pass

    def _timeline(
        self,
        session: dict[str, Any],
        event_type: str,
        *,
        details: dict[str, Any] | None = None,
        level: str = "INFO",
    ) -> dict[str, Any]:
        event = {
            "sequence": len(session["timeline"]) + 1,
            "timestamp": self._utc_now(),
            "type": event_type,
            "level": level,
            "details": details or {},
        }
        session["timeline"].append(event)
        session["updated_at"] = event["timestamp"]
        return event

    def _get(self, session_id: str | None = None) -> dict[str, Any]:
        resolved = session_id or self._active_session_id
        if not resolved or resolved not in self._sessions:
            raise WaterTestError("Session d'essai introuvable.")
        return self._sessions[resolved]

    def _assert_bridge_disarmed(self) -> None:
        bridge = getattr(
            self.controller, "controller_command_bridge", None
        )
        status_method = getattr(bridge, "status", None)
        if callable(status_method):
            status = status_method()
            if isinstance(status, dict) and status.get("armed") is True:
                raise WaterTestError(
                    "Le bridge doit rester désarmé en release 0.7.0."
                )

    def status(self) -> dict[str, Any]:
        with self._lock:
            active = (
                deepcopy(self._sessions.get(self._active_session_id))
                if self._active_session_id
                else None
            )
            return {
                "component": "water_test_framework",
                "version": self.VERSION,
                "running": True,
                "simulation_only": True,
                "physical_commands_allowed": False,
                "mqtt_publish_allowed": False,
                "active_session_id": self._active_session_id,
                "active_session": active,
                "session_count": len(self._sessions),
                "storage_path": str(self.storage_path),
                "started_at": self._started_at,
            }

    def scenarios(self) -> dict[str, Any]:
        return {
            "component": "water_test_framework",
            "count": len(self.SCENARIOS),
            "scenarios": deepcopy(self.SCENARIOS),
        }

    def create(
        self,
        *,
        scenario_id: str,
        operator: str,
        notes: str = "",
    ) -> dict[str, Any]:
        self._assert_bridge_disarmed()
        if scenario_id not in self.SCENARIOS:
            raise WaterTestError("Scénario inconnu.")
        operator = str(operator or "").strip()
        if not operator:
            raise WaterTestError("L'opérateur est obligatoire.")

        with self._lock:
            if self._active_session_id:
                active = self._sessions.get(self._active_session_id)
                if active and active["status"] not in self.TERMINAL_STATUSES:
                    raise WaterTestError(
                        "Une session active existe déjà."
                    )

            session_id = str(uuid.uuid4())
            now = self._utc_now()
            session = {
                "id": session_id,
                "version": self.VERSION,
                "scenario_id": scenario_id,
                "scenario": deepcopy(self.SCENARIOS[scenario_id]),
                "operator": operator[:200],
                "notes": str(notes or "")[:2000],
                "status": "CREATED",
                "created_at": now,
                "updated_at": now,
                "started_at": None,
                "finished_at": None,
                "simulation_only": True,
                "physical_commands_allowed": False,
                "timeline": [],
                "snapshots": [],
                "warnings": [],
                "result": None,
                "report": None,
            }
            self._timeline(session, "SESSION_CREATED")
            self._timeline(
                session,
                "SCENARIO_SELECTED",
                details={"scenario_id": scenario_id},
            )
            session["status"] = "READY"
            self._timeline(session, "SESSION_READY")
            self._sessions[session_id] = session
            self._active_session_id = session_id
            self._persist()
            result = deepcopy(session)

        self._publish("water_test.session.created", result)
        return result

    def start(self, *, session_id: str | None = None) -> dict[str, Any]:
        self._assert_bridge_disarmed()
        with self._lock:
            session = self._get(session_id)
            if session["status"] != "READY":
                raise WaterTestError(
                    "La session doit être READY pour démarrer."
                )
            session["status"] = "RUNNING"
            session["started_at"] = self._utc_now()
            baseline = self.digital_twin.snapshot(refresh=True)
            session["snapshots"].append(
                {
                    "label": "baseline",
                    "captured_at": self._utc_now(),
                    "state": baseline,
                }
            )
            self._timeline(session, "SESSION_STARTED")
            self._timeline(
                session,
                "DIGITAL_TWIN_BASELINE_CAPTURED",
            )
            self._persist()
            result = deepcopy(session)

        self._publish("water_test.session.started", result)
        return result

    def simulate_step(
        self,
        *,
        session_id: str | None = None,
        action: str,
        values: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        self._assert_bridge_disarmed()
        action = str(action or "").strip().upper()
        values = values or {}

        with self._lock:
            session = self._get(session_id)
            if session["status"] != "RUNNING":
                raise WaterTestError(
                    "La session doit être RUNNING."
                )

            allowed = {
                "CAPTURE_TWIN",
                "SIMULATE_VALVE_OPEN",
                "SIMULATE_VALVE_CLOSED",
                "SIMULATE_PUMP_ON",
                "SIMULATE_PUMP_OFF",
                "SIMULATE_FLOW",
                "SIMULATE_THERMAL",
                "SIMULATE_RUNNING",
                "SIMULATE_SHUTDOWN",
            }
            if action not in allowed:
                raise WaterTestError("Action de simulation inconnue.")

            if action == "SIMULATE_VALVE_OPEN":
                twin = self.digital_twin.apply_simulation(
                    valve_state="OPEN"
                )
            elif action == "SIMULATE_VALVE_CLOSED":
                twin = self.digital_twin.apply_simulation(
                    valve_state="CLOSED"
                )
            elif action == "SIMULATE_PUMP_ON":
                twin = self.digital_twin.apply_simulation(
                    pump_state="ON"
                )
            elif action == "SIMULATE_PUMP_OFF":
                twin = self.digital_twin.apply_simulation(
                    pump_state="OFF"
                )
            elif action == "SIMULATE_FLOW":
                twin = self.digital_twin.apply_simulation(
                    flow_l_min=float(values.get("flow_l_min", 12.0))
                )
            elif action == "SIMULATE_THERMAL":
                twin = self.digital_twin.apply_simulation(
                    source_in_c=float(values.get("source_in_c", 12.0)),
                    source_out_c=float(values.get("source_out_c", 14.0)),
                )
            elif action == "SIMULATE_RUNNING":
                twin = self.digital_twin.apply_simulation(
                    valve_state="OPEN",
                    pump_state="ON",
                    flow_l_min=float(values.get("flow_l_min", 12.0)),
                )
            elif action == "SIMULATE_SHUTDOWN":
                twin = self.digital_twin.apply_simulation(
                    valve_state="CLOSED",
                    pump_state="OFF",
                    flow_l_min=0.0,
                )
            else:
                twin = self.digital_twin.snapshot(refresh=False)

            snapshot = {
                "label": action.lower(),
                "captured_at": self._utc_now(),
                "state": twin,
            }
            session["snapshots"].append(snapshot)
            self._timeline(
                session,
                "SIMULATION_STEP_EXECUTED",
                details={
                    "action": action,
                    "values": self._safe(values),
                },
            )
            self._persist()
            result = {
                "session_id": session["id"],
                "status": session["status"],
                "action": action,
                "simulation_only": True,
                "physical_action_executed": False,
                "snapshot": deepcopy(snapshot),
            }

        self._publish("water_test.simulation.step", result)
        return result

    def finish(
        self,
        *,
        session_id: str | None = None,
        result: str = "PASS",
        notes: str = "",
    ) -> dict[str, Any]:
        self._assert_bridge_disarmed()
        result = str(result or "PASS").strip().upper()
        if result not in {"PASS", "FAIL", "INCONCLUSIVE"}:
            raise WaterTestError("Résultat invalide.")

        with self._lock:
            session = self._get(session_id)
            if session["status"] not in {"RUNNING", "PAUSED"}:
                raise WaterTestError(
                    "La session doit être RUNNING ou PAUSED."
                )
            final_state = self.digital_twin.snapshot(refresh=False)
            session["snapshots"].append(
                {
                    "label": "final",
                    "captured_at": self._utc_now(),
                    "state": final_state,
                }
            )
            session["status"] = (
                "FINISHED" if result != "FAIL" else "FAILED"
            )
            session["result"] = result
            session["finished_at"] = self._utc_now()
            if notes:
                session["notes"] = (
                    session["notes"] + "\n" + str(notes)
                ).strip()[:4000]
            self._timeline(
                session,
                "SESSION_FINISHED",
                details={"result": result},
                level="INFO" if result == "PASS" else "WARN",
            )
            session["report"] = self._build_report(session)
            if self._active_session_id == session["id"]:
                self._active_session_id = None
            self._persist()
            output = deepcopy(session)

        self._publish(
            "water_test.session.finished",
            output,
            "INFO" if result == "PASS" else "WARN",
        )
        return output

    def cancel(
        self,
        *,
        session_id: str | None = None,
        reason: str = "Annulation opérateur",
    ) -> dict[str, Any]:
        with self._lock:
            session = self._get(session_id)
            if session["status"] in self.TERMINAL_STATUSES:
                raise WaterTestError("La session est déjà terminée.")
            session["status"] = "ABORTED"
            session["finished_at"] = self._utc_now()
            session["result"] = "ABORTED"
            self._timeline(
                session,
                "SESSION_ABORTED",
                details={"reason": str(reason)[:1000]},
                level="WARN",
            )
            session["report"] = self._build_report(session)
            if self._active_session_id == session["id"]:
                self._active_session_id = None
            self._persist()
            result = deepcopy(session)

        self._publish("water_test.session.aborted", result, "WARN")
        return result

    def _build_report(self, session: dict[str, Any]) -> dict[str, Any]:
        started = session.get("started_at")
        finished = session.get("finished_at")
        duration_seconds = None
        if started and finished:
            try:
                start_dt = datetime.fromisoformat(started)
                finish_dt = datetime.fromisoformat(finished)
                duration_seconds = round(
                    (finish_dt - start_dt).total_seconds(), 3
                )
            except Exception:
                pass

        return {
            "report_type": "WATER_TEST_SIMULATION_REPORT",
            "version": self.VERSION,
            "generated_at": self._utc_now(),
            "session_id": session["id"],
            "scenario_id": session["scenario_id"],
            "operator": session["operator"],
            "status": session["status"],
            "result": session["result"],
            "duration_seconds": duration_seconds,
            "timeline_event_count": len(session["timeline"]),
            "snapshot_count": len(session["snapshots"]),
            "warning_count": len(session["warnings"]),
            "simulation_only": True,
            "physical_action_executed": False,
            "ready_for_physical_test": False,
            "recommendations": [
                "Valider les scénarios simulés avant la release 0.7.1.",
                "Conserver le bridge désarmé.",
                "Ne pas utiliser ce rapport comme certification hydraulique réelle.",
            ],
        }

    def session(self, session_id: str | None = None) -> dict[str, Any]:
        with self._lock:
            return deepcopy(self._get(session_id))

    def history(self, *, limit: int = 100) -> dict[str, Any]:
        limit = max(1, min(int(limit), 1000))
        with self._lock:
            items = sorted(
                self._sessions.values(),
                key=lambda item: item.get("created_at", ""),
                reverse=True,
            )[:limit]
            return {
                "component": "water_test_framework",
                "count": len(items),
                "limit": limit,
                "sessions": deepcopy(items),
            }

    def report(self, session_id: str) -> dict[str, Any]:
        with self._lock:
            session = self._get(session_id)
            return {
                "component": "water_test_framework",
                "session_id": session["id"],
                "available": session.get("report") is not None,
                "report": deepcopy(session.get("report")),
            }
