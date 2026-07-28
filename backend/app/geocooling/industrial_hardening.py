from __future__ import annotations

import copy
import json
import os
import threading
import time
import uuid
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


@dataclass
class TransactionStep:
    name: str
    action: Callable[[], Any]
    rollback: Callable[[], Any] | None = None


class GeoCoolingTransactionManager:
    """Executes ordered operations with reverse rollback on failure.

    This manager never arms hardware by itself. Callers provide explicit actions.
    """

    def __init__(self, history_capacity: int = 200, path: str | None = None) -> None:
        self.history_capacity = max(10, int(history_capacity))
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_TRANSACTION_PATH", str(base / "hardening-transactions.jsonl")))
        self._history: list[dict[str, Any]] = []
        self._lock = threading.RLock()
        self._load()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            items: list[dict[str, Any]] = []
            for line in self.path.read_text(encoding="utf-8").splitlines():
                if not line.strip():
                    continue
                value = json.loads(line)
                if isinstance(value, dict):
                    items.append(value)
            self._history = items[-self.history_capacity :]
        except Exception:
            self._history = []

    def _append(self, report: dict[str, Any]) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            with self.path.open("a", encoding="utf-8") as handle:
                handle.write(json.dumps(report, ensure_ascii=False) + "\n")
        except Exception:
            pass

    def execute(self, name: str, steps: list[TransactionStep], *, dry_run: bool = False) -> dict[str, Any]:
        transaction_id = uuid.uuid4().hex
        started = time.monotonic()
        completed: list[TransactionStep] = []
        records: list[dict[str, Any]] = []
        status = "DRY_RUN" if dry_run else "COMMITTED"
        error: str | None = None
        rollback_errors: list[str] = []

        try:
            for step in steps:
                step_started = time.monotonic()
                result = None if dry_run else step.action()
                completed.append(step)
                records.append({
                    "name": step.name,
                    "status": "SIMULATED" if dry_run else "OK",
                    "duration_ms": round((time.monotonic() - step_started) * 1000, 3),
                    "result": result,
                })
        except Exception as exc:
            status = "ROLLED_BACK"
            error = f"{type(exc).__name__}: {exc}"
            records.append({"name": getattr(step, "name", "unknown"), "status": "FAILED", "error": error})
            for completed_step in reversed(completed):
                if completed_step.rollback is None:
                    continue
                try:
                    completed_step.rollback()
                except Exception as rollback_exc:
                    rollback_errors.append(f"{completed_step.name}: {rollback_exc}")
            if rollback_errors:
                status = "ROLLBACK_FAILED"

        report = {
            "transaction_id": transaction_id,
            "name": str(name),
            "started_at": utc_now_iso(),
            "status": status,
            "dry_run": bool(dry_run),
            "duration_ms": round((time.monotonic() - started) * 1000, 3),
            "steps": records,
            "error": error,
            "rollback_errors": rollback_errors,
        }
        with self._lock:
            self._history.append(copy.deepcopy(report))
            self._history = self._history[-self.history_capacity :]
            self._append(report)
        return report

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._history[-max(1, int(limit)) :])

    def status(self) -> dict[str, Any]:
        history = self.history(self.history_capacity)
        return {
            "generated_at": utc_now_iso(),
            "transactions": len(history),
            "committed": sum(1 for item in history if item["status"] == "COMMITTED"),
            "rolled_back": sum(1 for item in history if item["status"] in {"ROLLED_BACK", "ROLLBACK_FAILED"}),
            "last": history[-1] if history else None,
        }


class GeoCoolingHeartbeatRegistry:
    def __init__(self, stale_after_seconds: float = 120.0) -> None:
        self.stale_after_seconds = max(1.0, float(stale_after_seconds))
        self._components: dict[str, dict[str, Any]] = {}
        self._lock = threading.RLock()

    def beat(self, component: str, *, status: str = "OK", details: dict[str, Any] | None = None) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            previous = self._components.get(component, {})
            item = {
                "component": component,
                "status": str(status).upper(),
                "last_seen_at": utc_now_iso(),
                "last_seen_epoch": now,
                "beats": int(previous.get("beats", 0)) + 1,
                "errors": int(previous.get("errors", 0)) + (1 if str(status).upper() == "ERROR" else 0),
                "details": details or {},
            }
            self._components[component] = item
            return copy.deepcopy(item)

    def snapshot(self) -> dict[str, Any]:
        now = time.time()
        with self._lock:
            items = []
            for item in self._components.values():
                current = copy.deepcopy(item)
                age = max(0.0, now - float(current["last_seen_epoch"]))
                current["age_seconds"] = round(age, 3)
                current["healthy"] = current["status"] == "OK" and age <= self.stale_after_seconds
                current.pop("last_seen_epoch", None)
                items.append(current)
        items.sort(key=lambda value: value["component"])
        return {
            "generated_at": utc_now_iso(),
            "stale_after_seconds": self.stale_after_seconds,
            "healthy": bool(items) and all(item["healthy"] for item in items),
            "count": len(items),
            "components": items,
        }


class GeoCoolingLifecycleRegistry:
    STATES = {"INIT", "READY", "DEGRADED", "FAILED", "RECOVERING", "STOPPED"}

    def __init__(self, path: str | None = None, history_capacity: int = 500) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_LIFECYCLE_PATH", str(base / "component-lifecycle.json")))
        self.history_capacity = max(50, int(history_capacity))
        self._lock = threading.RLock()
        self._components: dict[str, dict[str, Any]] = {}
        self._history: list[dict[str, Any]] = []
        self._boot_id = uuid.uuid4().hex
        self._previous_boot_id: str | None = None
        self._started_at = utc_now_iso()
        self._load()
        self._persist()

    def _load(self) -> None:
        try:
            if not self.path.exists():
                return
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data, dict):
                self._previous_boot_id = data.get("boot_id")
                components = data.get("components")
                history = data.get("history")
                if isinstance(components, dict):
                    self._components = components
                if isinstance(history, list):
                    self._history = history[-self.history_capacity :]
        except Exception:
            self._components = {}
            self._history = []

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            payload = {
                "version": "H002-1.0",
                "boot_id": self._boot_id,
                "previous_boot_id": self._previous_boot_id,
                "started_at": self._started_at,
                "updated_at": utc_now_iso(),
                "components": self._components,
                "history": self._history[-self.history_capacity :],
            }
            temporary = self.path.with_suffix(".tmp")
            temporary.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except Exception:
            pass

    def transition(self, component: str, state: str, *, reason: str, details: dict[str, Any] | None = None) -> dict[str, Any]:
        state = str(state).upper()
        if state not in self.STATES:
            raise ValueError(f"Unsupported lifecycle state: {state}")
        name = str(component).strip()
        if not name:
            raise ValueError("A component name is required")
        with self._lock:
            previous = self._components.get(name, {}).get("state")
            event = {
                "component": name,
                "from": previous,
                "to": state,
                "reason": str(reason),
                "details": details or {},
                "at": utc_now_iso(),
                "boot_id": self._boot_id,
            }
            self._components[name] = {
                "component": name,
                "state": state,
                "reason": str(reason),
                "details": details or {},
                "updated_at": event["at"],
                "boot_id": self._boot_id,
            }
            if previous != state or not self._history:
                self._history.append(event)
                self._history = self._history[-self.history_capacity :]
            self._persist()
            return copy.deepcopy(self._components[name])

    def snapshot(self) -> dict[str, Any]:
        with self._lock:
            items = sorted((copy.deepcopy(v) for v in self._components.values()), key=lambda x: x["component"])
            return {
                "generated_at": utc_now_iso(),
                "version": "H002-1.0",
                "boot_id": self._boot_id,
                "previous_boot_id": self._previous_boot_id,
                "restart_detected": bool(self._previous_boot_id and self._previous_boot_id != self._boot_id),
                "started_at": self._started_at,
                "healthy": bool(items) and all(item["state"] == "READY" for item in items),
                "components": items,
                "history_count": len(self._history),
                "last_transition": copy.deepcopy(self._history[-1]) if self._history else None,
            }

    def history(self, limit: int = 100) -> list[dict[str, Any]]:
        with self._lock:
            return copy.deepcopy(self._history[-max(1, int(limit)) :])


class GeoCoolingSafeMode:
    def __init__(self, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_SAFE_MODE_PATH", str(base / "safe-mode.json")))
        self._lock = threading.RLock()
        self._state = {
            "active": False,
            "reason": None,
            "activated_at": None,
            "activated_by": None,
            "updated_at": utc_now_iso(),
        }
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                data = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(data, dict):
                    self._state.update(data)
        except Exception:
            pass

    def _persist(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        temporary = self.path.with_suffix(".tmp")
        temporary.write_text(json.dumps(self._state, ensure_ascii=False, indent=2), encoding="utf-8")
        temporary.replace(self.path)

    def activate(self, reason: str, activated_by: str = "system") -> dict[str, Any]:
        if not str(reason).strip():
            raise ValueError("A safe-mode reason is required")
        with self._lock:
            self._state.update({
                "active": True,
                "reason": str(reason).strip(),
                "activated_at": utc_now_iso(),
                "activated_by": str(activated_by).strip() or "system",
                "updated_at": utc_now_iso(),
            })
            self._persist()
            return self.status()

    def clear(self, cleared_by: str = "operator") -> dict[str, Any]:
        with self._lock:
            self._state.update({
                "active": False,
                "reason": None,
                "activated_at": None,
                "activated_by": None,
                "cleared_by": str(cleared_by).strip() or "operator",
                "updated_at": utc_now_iso(),
            })
            self._persist()
            return self.status()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state)


class GeoCoolingIndustrialHardening:
    VERSION = "H002-1.0"

    def __init__(self, *, controller: Any, watchdog: Any, runtime: Any, integration_audit: Any, runtime_profiler: Any, operations_suite: Any, hardware_manual_control: Any) -> None:
        self.controller = controller
        self.watchdog = watchdog
        self.runtime = runtime
        self.integration_audit = integration_audit
        self.runtime_profiler = runtime_profiler
        self.operations_suite = operations_suite
        self.hardware_manual_control = hardware_manual_control
        self.transactions = GeoCoolingTransactionManager()
        self.lifecycle = GeoCoolingLifecycleRegistry()
        self._startup_self_test: dict[str, Any] | None = None
        self._startup_lock = threading.RLock()
        self.heartbeats = GeoCoolingHeartbeatRegistry(
            stale_after_seconds=float(os.getenv("GEOCOOLING_HEARTBEAT_STALE_SECONDS", "180"))
        )
        self.safe_mode = GeoCoolingSafeMode()
        self.run_startup_self_test()

    @staticmethod
    def _safe(callable_: Callable[[], Any]) -> dict[str, Any]:
        started = time.monotonic()
        try:
            data = callable_()
            return {"ok": True, "duration_ms": round((time.monotonic() - started) * 1000, 3), "data": data}
        except Exception as exc:
            return {"ok": False, "duration_ms": round((time.monotonic() - started) * 1000, 3), "error": f"{type(exc).__name__}: {exc}"}

    def probe(self) -> dict[str, Any]:
        probes = {
            "controller": self._safe(self.controller.status),
            "watchdog": self._safe(self.watchdog.evaluate),
            "runtime": self._safe(self.runtime.status),
            "integration_audit": self._safe(self.integration_audit.status),
            "runtime_profiler": self._safe(self.runtime_profiler.status),
            "operations_suite": self._safe(self.operations_suite.readiness),
            "hardware_manual": self._safe(self.hardware_manual_control.status),
        }
        for name, probe in probes.items():
            status = "OK" if probe["ok"] else "ERROR"
            self.heartbeats.beat(name, status=status, details={"duration_ms": probe["duration_ms"], "error": probe.get("error")})
            self.lifecycle.transition(
                name,
                "READY" if probe["ok"] else "FAILED",
                reason="probe successful" if probe["ok"] else str(probe.get("error", "probe failed")),
                details={"duration_ms": probe["duration_ms"]},
            )
        return {"generated_at": utc_now_iso(), "probes": probes, "heartbeat": self.heartbeats.snapshot(), "lifecycle": self.lifecycle.snapshot()}

    def run_startup_self_test(self) -> dict[str, Any]:
        with self._startup_lock:
            for name in ("controller", "watchdog", "runtime", "integration_audit", "runtime_profiler", "operations_suite", "hardware_manual"):
                self.lifecycle.transition(name, "INIT", reason="startup self-test")
            probe = self.probe()
            failed = [name for name, result in probe["probes"].items() if not result["ok"]]
            hardware = probe["probes"].get("hardware_manual", {}).get("data") or {}
            hardware_safe = not bool(hardware.get("armed"))
            status = "PASS" if not failed and hardware_safe else "FAIL"
            if status == "FAIL":
                self.safe_mode.activate(
                    "; ".join(failed) if failed else "hardware armed during startup",
                    "startup-self-test",
                )
            self._startup_self_test = {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "status": status,
                "failed_components": failed,
                "hardware_safe": hardware_safe,
                "restart_detected": self.lifecycle.snapshot()["restart_detected"],
                "safe_mode": self.safe_mode.status(),
            }
            return copy.deepcopy(self._startup_self_test)

    def startup_status(self) -> dict[str, Any]:
        with self._startup_lock:
            return copy.deepcopy(self._startup_self_test or self.run_startup_self_test())

    def recovery_report(self) -> dict[str, Any]:
        lifecycle = self.lifecycle.snapshot()
        safe_mode = self.safe_mode.status()
        startup = self.startup_status()
        transactions = self.transactions.status()
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "restart_detected": lifecycle["restart_detected"],
            "startup_self_test": startup,
            "safe_mode": safe_mode,
            "transactions": transactions,
            "recovery_required": bool(safe_mode.get("active")) or startup.get("status") != "PASS",
            "hardware_remains_disarmed": True,
        }

    def evaluate_safe_mode(self, probe: dict[str, Any] | None = None) -> dict[str, Any]:
        probe = probe or self.probe()
        failed = [name for name, result in probe["probes"].items() if not result["ok"]]
        hardware = probe["probes"].get("hardware_manual", {}).get("data") or {}
        critical = len(failed) >= 2 or bool(hardware.get("fault"))
        if critical and not self.safe_mode.status()["active"]:
            self.safe_mode.activate("; ".join(failed) if failed else "hardware fault", "hardening-engine")
            try:
                if bool(hardware.get("armed")):
                    self.hardware_manual_control.disarm(requested_by="hardening-engine")
            except Exception:
                pass
        return {"critical": critical, "failed_components": failed, "safe_mode": self.safe_mode.status()}

    def certification(self, *, refresh: bool = True) -> dict[str, Any]:
        probe = self.probe() if refresh else {"heartbeat": self.heartbeats.snapshot(), "probes": {}}
        safe = self.evaluate_safe_mode(probe)
        audit = probe["probes"].get("integration_audit", {}).get("data") or {}
        readiness = probe["probes"].get("operations_suite", {}).get("data") or {}
        heartbeat = probe["heartbeat"]
        checks = [
            {"name": "component-probes", "pass": all(item["ok"] for item in probe["probes"].values())},
            {"name": "heartbeats", "pass": bool(heartbeat.get("healthy"))},
            {"name": "integration-audit", "pass": not bool(audit.get("blockers"))},
            {"name": "software-readiness", "pass": bool(readiness.get("software_ready"))},
            {"name": "safe-mode-clear", "pass": not bool(safe["safe_mode"].get("active"))},
            {"name": "hardware-autostart-disabled", "pass": not bool((probe["probes"].get("hardware_manual", {}).get("data") or {}).get("armed"))},
        ]
        passed = sum(1 for check in checks if check["pass"])
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": "PASS" if passed == len(checks) else "FAIL",
            "score_percent": round(100 * passed / len(checks), 1),
            "ready_for_field_deployment": passed == len(checks),
            "checks": checks,
            "safe_mode": safe["safe_mode"],
            "heartbeat": heartbeat,
        }

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "safe_mode": self.safe_mode.status(),
            "heartbeat": self.heartbeats.snapshot(),
            "transactions": self.transactions.status(),
            "lifecycle": self.lifecycle.snapshot(),
            "startup_self_test": self.startup_status(),
        }
