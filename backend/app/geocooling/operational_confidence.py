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


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        parsed = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


class GeoCoolingOperationalConfidenceManager:
    """Evaluates telemetry freshness, sensor drift and operational confidence.

    This manager is read-only with regard to hardware. It can only publish a
    software lock recommendation; it never arms or commands outputs.
    """

    VERSION = "H013-OPERATIONAL-CONFIDENCE-1.0"
    REQUIRED_SENSORS = (
        "indoor_temperature_c",
        "indoor_humidity_percent",
        "supply_temperature_c",
        "return_temperature_c",
        "source_in_temperature_c",
        "source_out_temperature_c",
    )
    MAX_AGE_SECONDS = 300
    DRIFT_LIMITS_PER_HOUR = {
        "indoor_temperature_c": 3.0,
        "indoor_humidity_percent": 20.0,
        "supply_temperature_c": 12.0,
        "return_temperature_c": 12.0,
        "source_in_temperature_c": 8.0,
        "source_out_temperature_c": 8.0,
        "flow_l_min": 50.0,
    }

    def __init__(self, journal: Any, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv(
            "GEOCOOLING_OPERATIONAL_CONFIDENCE_PATH",
            str(base / "operational-confidence-h013.json"),
        ))
        self.journal = journal
        self._lock = threading.RLock()
        self._last_report: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(payload, dict):
                    self._last_report = payload.get("last_report")
        except Exception:
            self._last_report = None

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(".tmp")
            tmp.write_text(json.dumps({"last_report": self._last_report}, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def evaluate(
        self,
        *,
        latest: dict[str, Any] | None,
        previous: dict[str, Any] | None,
        quality: dict[str, Any] | None,
        physical_mode: bool,
        now: datetime | None = None,
    ) -> dict[str, Any]:
        latest = latest or {}
        previous = previous or {}
        quality = quality or {}
        now = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)

        timestamp = _parse_timestamp(latest.get("timestamp"))
        age_seconds = None if timestamp is None else max(0.0, (now - timestamp).total_seconds())
        freshness_status = "UNKNOWN" if age_seconds is None else ("PASS" if age_seconds <= self.MAX_AGE_SECONDS else "FAIL")

        missing_required = [sensor for sensor in self.REQUIRED_SENSORS if _finite(latest.get(sensor)) is None]

        drift_checks: list[dict[str, Any]] = []
        drift_failures: list[dict[str, Any]] = []
        previous_ts = _parse_timestamp(previous.get("timestamp"))
        elapsed_hours = None
        if timestamp is not None and previous_ts is not None:
            elapsed_hours = (timestamp - previous_ts).total_seconds() / 3600.0
            if elapsed_hours <= 0:
                elapsed_hours = None

        for sensor, limit in self.DRIFT_LIMITS_PER_HOUR.items():
            current_value = _finite(latest.get(sensor))
            previous_value = _finite(previous.get(sensor))
            if current_value is None or previous_value is None or elapsed_hours is None:
                check = {"sensor": sensor, "status": "UNKNOWN", "rate_per_hour": None, "limit_per_hour": limit}
            else:
                rate = abs(current_value - previous_value) / elapsed_hours
                status = "PASS" if rate <= limit else "FAIL"
                check = {
                    "sensor": sensor,
                    "status": status,
                    "rate_per_hour": round(rate, 3),
                    "limit_per_hour": limit,
                }
                if status == "FAIL":
                    drift_failures.append(check)
            drift_checks.append(check)

        score = 100
        blockers: list[str] = []
        warnings: list[str] = []

        if freshness_status == "FAIL":
            score -= 35
            blockers.append("stale-telemetry")
        elif freshness_status == "UNKNOWN":
            score -= 20
            warnings.append("telemetry-timestamp-unknown")

        if missing_required:
            penalty = min(40, 7 * len(missing_required))
            score -= penalty
            (blockers if physical_mode else warnings).append("required-sensors-missing")

        quality_status = str(quality.get("status") or "NOT_EVALUATED")
        if quality_status == "FAIL":
            score -= 35
            blockers.append("data-quality-failed")
        elif quality_status in {"DEGRADED", "NOT_EVALUATED"}:
            score -= 15
            warnings.append("data-quality-degraded")

        if drift_failures:
            score -= min(30, 10 * len(drift_failures))
            blockers.append("sensor-drift-detected")

        score = max(0, min(100, score))
        if blockers:
            confidence = "LOW"
        elif score >= 85:
            confidence = "HIGH"
        elif score >= 65:
            confidence = "MEDIUM"
        else:
            confidence = "LOW"

        automatic_mode_allowed = bool(
            physical_mode
            and not blockers
            and score >= 85
            and not missing_required
            and freshness_status == "PASS"
            and quality_status == "PASS"
        )

        report = {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "confidence_score": score,
            "confidence_level": confidence,
            "freshness": {
                "status": freshness_status,
                "age_seconds": None if age_seconds is None else round(age_seconds, 1),
                "maximum_age_seconds": self.MAX_AGE_SECONDS,
            },
            "missing_required_sensors": missing_required,
            "drift_checks": drift_checks,
            "drift_failures": drift_failures,
            "quality_status": quality_status,
            "blocking_conditions": sorted(set(blockers)),
            "warnings": sorted(set(warnings)),
            "physical_mode": bool(physical_mode),
            "automatic_mode_allowed": automatic_mode_allowed,
            "software_interlock_required": not automatic_mode_allowed,
            "physical_activation_allowed": False,
            "hardware_touched": False,
        }
        with self._lock:
            previous_report = self._last_report
            self._last_report = report
            self._persist()
        if blockers and (not previous_report or previous_report.get("blocking_conditions") != report["blocking_conditions"]):
            self.journal.record(
                "operational_confidence",
                "software_interlock_required",
                level="ERROR",
                details={"blocking_conditions": report["blocking_conditions"], "score": score},
            )
        return copy.deepcopy(report)

    def status(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._last_report or {
                "generated_at": utc_now_iso(),
                "version": self.VERSION,
                "confidence_score": 0,
                "confidence_level": "UNKNOWN",
                "automatic_mode_allowed": False,
                "software_interlock_required": True,
                "physical_activation_allowed": False,
                "hardware_touched": False,
            })
