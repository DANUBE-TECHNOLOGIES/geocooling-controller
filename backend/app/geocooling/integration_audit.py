from __future__ import annotations

import importlib.util
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _safe_call(callable_: Callable[[], Any]) -> tuple[bool, Any]:
    try:
        return True, callable_()
    except Exception as exc:
        return False, f"{type(exc).__name__}: {exc}"


class GeoCoolingIntegrationAudit:
    """Audit C024.1 strictement en lecture seule."""

    VERSION = "C024.2"
    REQUIRED_MODULES = (
        "brain", "decision_journal", "operations_dashboard",
        "hardware_manual_control", "waveshare_modbus_driver",
        "thermal_forecast", "digital_twin", "digital_twin_calibration",
        "efficiency_index", "drift_detector", "assisted_calibration",
        "controller_safety_gate", "execution_supervisor",
    )
    REQUIRED_ROUTES = (
        "/geocooling/dashboard", "/geocooling/manual/hardware/status",
        "/geocooling/brain/history", "/geocooling/brain/metrics",
        "/geocooling/brain/journal/status", "/geocooling/brain/forecast",
        "/geocooling/brain/scenarios", "/geocooling/digital-twin/model",
        "/geocooling/digital-twin/calibration/status",
        "/geocooling/performance/gei", "/geocooling/performance/drift",
        "/geocooling/performance/calibration/status",
    )

    def __init__(self, controller: Any, hardware_manual_control: Any,
                 operations_dashboard: Any, *,
                 route_provider: Callable[[], list[str]] | None = None,
                 base_package: str = "app.geocooling") -> None:
        self.controller = controller
        self.hardware_manual_control = hardware_manual_control
        self.operations_dashboard = operations_dashboard
        self.route_provider = route_provider
        self.base_package = base_package
        self.last_report: dict[str, Any] | None = None

    def _check(self, check_id: str, category: str, ok: bool, detail: str,
               *, blocking: bool = True) -> dict[str, Any]:
        return {"id": check_id, "category": category,
                "status": "PASS" if ok else "FAIL",
                "blocking": bool(blocking), "detail": detail}

    def _module_checks(self) -> list[dict[str, Any]]:
        return [self._check(f"module:{name}", "architecture",
                            importlib.util.find_spec(f"{self.base_package}.{name}") is not None,
                            f"{self.base_package}.{name}")
                for name in self.REQUIRED_MODULES]

    def _route_checks(self) -> list[dict[str, Any]]:
        if self.route_provider is None:
            return [self._check("routes:provider", "api", False,
                                "Fournisseur de routes absent")]
        ok, value = _safe_call(self.route_provider)
        if not ok:
            return [self._check("routes:provider", "api", False, str(value))]
        routes = set(value or [])
        return [self._check(f"route:{path}", "api", path in routes, path)
                for path in self.REQUIRED_ROUTES]

    def _runtime_checks(self) -> list[dict[str, Any]]:
        checks: list[dict[str, Any]] = []
        driver_name = str(getattr(self.controller, "driver_name", "unknown"))
        autopilot_enabled = bool(getattr(self.controller, "autopilot_enabled", False))
        allow_real = bool(getattr(self.controller, "autopilot_allow_real_driver", False))
        checks.append(self._check("runtime:controller", "runtime",
                                  self.controller is not None,
                                  "Contrôleur instancié"))
        checks.append(self._check(
            "runtime:autopilot-safe", "safety",
            not (driver_name != "simulation" and autopilot_enabled and allow_real),
            f"driver={driver_name}, autopilot={autopilot_enabled}, allow_real={allow_real}"))
        ok, hardware = _safe_call(self.hardware_manual_control.status)
        checks.append(self._check("runtime:manual-status", "hardware",
                                  ok and isinstance(hardware, dict), str(hardware)))
        if ok and isinstance(hardware, dict):
            armed = bool(hardware.get("armed", False))
            checks.append(self._check("runtime:hardware-disarmed", "safety",
                                      not armed, f"armed={armed}", blocking=False))
        ok, dashboard = _safe_call(self.operations_dashboard.snapshot)
        checks.append(self._check("runtime:dashboard", "runtime",
                                  ok and isinstance(dashboard, dict),
                                  "Dashboard lisible" if ok else str(dashboard)))
        return checks

    def _persistence_checks(self) -> list[dict[str, Any]]:
        data_dir = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        checks: list[dict[str, Any]] = []

        checks.append(self._check(
            "persistence:data-directory", "persistence",
            data_dir.exists() and data_dir.is_dir(), str(data_dir),
        ))

        probe = data_dir / ".geocooling-write-probe"
        writable = False
        detail = f"writable=False: {data_dir}"
        try:
            data_dir.mkdir(parents=True, exist_ok=True)
            probe.write_text("c0242", encoding="utf-8")
            if probe.read_text(encoding="utf-8") == "c0242":
                writable = True
                detail = f"writable=True: {data_dir}"
        except OSError as exc:
            detail = f"writable=False: {data_dir}: {type(exc).__name__}: {exc}"
        finally:
            try:
                probe.unlink(missing_ok=True)
            except OSError:
                pass

        checks.append(self._check(
            "persistence:writable", "persistence", writable, detail,
        ))

        journal_path = Path(os.getenv(
            "GEOCOOLING_BRAIN_JOURNAL_PATH",
            str(data_dir / "brain-decisions.jsonl"),
        ))
        consistent = journal_path.parent == data_dir
        checks.append(self._check(
            "persistence:journal-location", "persistence", consistent,
            f"journal={journal_path}; data_dir={data_dir}",
            blocking=False,
        ))
        return checks

    def evaluate(self) -> dict[str, Any]:
        checks = (self._module_checks() + self._route_checks() +
                  self._runtime_checks() + self._persistence_checks())
        blocking_failures = [c for c in checks if c["status"] == "FAIL" and c["blocking"]]
        warnings = [c for c in checks if c["status"] == "FAIL" and not c["blocking"]]
        verdict = "READY_FOR_COMMISSIONING" if not blocking_failures else "NOT_READY"
        report = {
            "version": self.VERSION, "generated_at": _utc_now(),
            "verdict": verdict, "ready": verdict == "READY_FOR_COMMISSIONING",
            "summary": {"total": len(checks),
                        "passed": sum(c["status"] == "PASS" for c in checks),
                        "failed": sum(c["status"] == "FAIL" for c in checks),
                        "blocking_failures": len(blocking_failures),
                        "warnings": len(warnings)},
            "scope": "software_integration_pre_commissioning",
            "hardware_certification_required_separately": True,
            "checks": checks, "blocking_failures": blocking_failures,
            "warnings": warnings,
        }
        self.last_report = report
        return report

    def status(self) -> dict[str, Any]:
        return self.last_report or self.evaluate()
