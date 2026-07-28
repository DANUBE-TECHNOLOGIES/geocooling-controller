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


def _number(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class GeoCoolingSensorQualityManager:
    """Persistent calibration and read-only telemetry quality assessment."""

    VERSION = "H012-DATA-QUALITY-1.0"
    DEFAULT_RANGES = {
        "indoor_temperature_c": (5.0, 40.0),
        "indoor_humidity_percent": (10.0, 95.0),
        "floor_surface_temperature_c": (5.0, 35.0),
        "supply_temperature_c": (4.0, 40.0),
        "return_temperature_c": (4.0, 40.0),
        "source_in_temperature_c": (0.0, 35.0),
        "source_out_temperature_c": (0.0, 40.0),
        "flow_l_min": (0.0, 80.0),
        "outdoor_temperature_c": (-20.0, 50.0),
    }

    def __init__(self, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_SENSOR_QUALITY_PATH", str(base / "sensor-quality-h012.json")))
        self.journal = journal
        self._lock = threading.RLock()
        self._calibrations: dict[str, dict[str, Any]] = {}
        self._last_report: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._calibrations = payload.get("calibrations") or {}
                    self._last_report = payload.get("last_report")
        except Exception:
            self._calibrations = {}
            self._last_report = None

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({
                "calibrations": self._calibrations,
                "last_report": self._last_report,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def set_calibration(self, sensor: str, *, offset: float, operator: str, note: str = "") -> dict[str, Any]:
        sensor = str(sensor).strip()
        if sensor not in self.DEFAULT_RANGES:
            raise ValueError(f"Unsupported sensor: {sensor}")
        numeric = _number(offset)
        if numeric is None or abs(numeric) > 5.0:
            raise ValueError("Calibration offset must be finite and between -5.0 and +5.0")
        item = {
            "sensor": sensor,
            "offset": round(numeric, 3),
            "operator": str(operator or "operator"),
            "note": str(note),
            "updated_at": utc_now_iso(),
            "application": "TELEMETRY_NORMALIZATION_ONLY",
        }
        with self._lock:
            self._calibrations[sensor] = item
            self._persist()
        self.journal.record("data_quality", "calibration_updated", details=item)
        return copy.deepcopy(item)

    def apply_calibration(self, observation: dict[str, Any]) -> dict[str, Any]:
        result = copy.deepcopy(observation)
        with self._lock:
            calibrations = copy.deepcopy(self._calibrations)
        for sensor, item in calibrations.items():
            value = _number(result.get(sensor))
            if value is not None:
                result[sensor] = round(value + float(item.get("offset", 0.0)), 3)
        return result

    def assess(self, observation: dict[str, Any] | None, previous: dict[str, Any] | None = None) -> dict[str, Any]:
        observation = observation or {}
        previous = previous or {}
        checks: list[dict[str, Any]] = []
        failures: list[dict[str, Any]] = []
        warnings: list[dict[str, Any]] = []
        present = 0
        for sensor, (minimum, maximum) in self.DEFAULT_RANGES.items():
            value = _number(observation.get(sensor))
            if value is None:
                check = {"sensor": sensor, "status": "MISSING", "value": None}
                checks.append(check)
                warnings.append(check)
                continue
            present += 1
            status = "PASS" if minimum <= value <= maximum else "FAIL"
            check = {"sensor": sensor, "status": status, "value": value, "minimum": minimum, "maximum": maximum}
            previous_value = _number(previous.get(sensor))
            if status == "PASS" and previous_value is not None and value == previous_value:
                check["unchanged"] = True
            checks.append(check)
            if status == "FAIL":
                failures.append(check)
        coverage = round(100.0 * present / len(self.DEFAULT_RANGES), 1)
        status = "FAIL" if failures else ("DEGRADED" if coverage < 50.0 else "PASS")
        report = {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": status,
            "coverage_percent": coverage,
            "present_sensor_count": present,
            "expected_sensor_count": len(self.DEFAULT_RANGES),
            "failures": failures,
            "warnings": warnings,
            "checks": checks,
            "calibrations": copy.deepcopy(self._calibrations),
            "physical_activation_allowed": False,
            "hardware_touched": False,
        }
        with self._lock:
            self._last_report = report
            self._persist()
        if failures:
            self.journal.record("data_quality", "invalid_sensor_values", level="ERROR", details={"failures": failures})
        return copy.deepcopy(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._last_report or {
                "generated_at": utc_now_iso(), "version": self.VERSION, "status": "NOT_EVALUATED",
                "coverage_percent": 0.0, "calibrations": self._calibrations,
                "physical_activation_allowed": False, "hardware_touched": False,
            })
