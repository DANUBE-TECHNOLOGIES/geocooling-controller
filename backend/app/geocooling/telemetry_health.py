"""GeoCooling telemetry-role health classification.

Pure read-only helpers used to distinguish configuration errors from upstream
sensor/metric loss.  This module never publishes MQTT messages and never
commands any actuator.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence


ROLE_SPECS: dict[str, dict[str, str]] = {
    "surface": {
        "env": "GEOCOOLING_SURFACE_SENSOR",
        "metric": "temperature",
    },
    "floor_supply": {
        "env": "GEOCOOLING_FLOOR_SUPPLY_SENSOR",
        "metric": "temperature",
    },
    "floor_return": {
        "env": "GEOCOOLING_FLOOR_RETURN_SENSOR",
        "metric": "temperature",
    },
    "source_inlet": {
        "env": "GEOCOOLING_SOURCE_INLET_SENSOR",
        "metric": "temperature",
    },
    "source_outlet": {
        "env": "GEOCOOLING_SOURCE_OUTLET_SENSOR",
        "metric": "temperature",
    },
    "flow": {
        "env": "GEOCOOLING_FLOW_SENSOR",
        "metric": "flow",
    },
}


def _parse_timestamp(value: Any) -> datetime | None:
    if not value:
        return None
    if isinstance(value, datetime):
        parsed = value
    else:
        text = str(value).strip()
        if not text:
            return None
        if text.endswith("Z"):
            text = text[:-1] + "+00:00"
        try:
            parsed = datetime.fromisoformat(text)
        except ValueError:
            return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _age_seconds(measured_at: Any, now: datetime) -> float | None:
    parsed = _parse_timestamp(measured_at)
    if parsed is None:
        return None
    return max(0.0, (now - parsed).total_seconds())


def classify_role(
    *,
    role: str,
    sensor_name: str | None,
    metric: str,
    rows: Sequence[Mapping[str, Any]],
    stale_seconds: int = 120,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Classify one role as UNSET/SOURCE_ABSENT/METRIC_ABSENT/STALE/OK."""

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    configured_sensor = (sensor_name or "").strip()

    base = {
        "role": role,
        "sensor_name": configured_sensor or None,
        "metric": metric,
        "stale_seconds": int(stale_seconds),
        "measured_at": None,
        "age_seconds": None,
        "value": None,
        "unit": None,
        "mqtt_topic": None,
    }

    if not configured_sensor:
        return {
            **base,
            "state": "UNSET",
            "ready": False,
            "reason": "No sensor is configured for this GeoCooling role.",
        }

    sensor_rows = [
        row
        for row in rows
        if str(row.get("sensor_name") or "").strip() == configured_sensor
    ]

    if not sensor_rows:
        return {
            **base,
            "state": "SOURCE_ABSENT",
            "ready": False,
            "reason": "Configured sensor has not been observed upstream.",
        }

    metric_rows = [
        row
        for row in sensor_rows
        if str(row.get("metric") or "").strip() == metric
    ]

    if not metric_rows:
        return {
            **base,
            "state": "METRIC_ABSENT",
            "ready": False,
            "reason": "Sensor is observed but the required metric is absent.",
        }

    def sort_key(row: Mapping[str, Any]) -> datetime:
        parsed = _parse_timestamp(row.get("measured_at"))
        return parsed or datetime.min.replace(tzinfo=timezone.utc)

    latest = max(metric_rows, key=sort_key)
    age = _age_seconds(latest.get("measured_at"), current_time)

    observed = {
        **base,
        "measured_at": latest.get("measured_at"),
        "age_seconds": round(age, 3) if age is not None else None,
        "value": latest.get("value"),
        "unit": latest.get("unit"),
        "mqtt_topic": latest.get("mqtt_topic"),
    }

    if age is None or age > stale_seconds:
        return {
            **observed,
            "state": "STALE",
            "ready": False,
            "reason": "Required metric is present but not fresh enough.",
        }

    return {
        **observed,
        "state": "OK",
        "ready": True,
        "reason": "Required metric is present and fresh.",
    }


def build_telemetry_health(
    rows: Sequence[Mapping[str, Any]],
    *,
    mappings: Mapping[str, str | None] | None = None,
    stale_seconds: int | None = None,
    now: datetime | None = None,
) -> dict[str, Any]:
    """Build a fail-closed health report for all six GeoCooling roles."""

    threshold = int(
        stale_seconds
        if stale_seconds is not None
        else os.getenv("GEOCOOLING_SENSOR_STALE_SECONDS", "120")
    )
    supplied = mappings or {}

    role_results: dict[str, dict[str, Any]] = {}
    for role, spec in ROLE_SPECS.items():
        sensor_name = (
            supplied.get(role)
            if role in supplied
            else os.getenv(spec["env"])
        )
        role_results[role] = classify_role(
            role=role,
            sensor_name=sensor_name,
            metric=spec["metric"],
            rows=rows,
            stale_seconds=threshold,
            now=now,
        )

    observed_sensors = sorted(
        {
            str(row.get("sensor_name") or "").strip()
            for row in rows
            if str(row.get("sensor_name") or "").strip()
        }
    )
    hydraulic_candidates = sorted(
        {
            str(row.get("sensor_name") or "").strip()
            for row in rows
            if str(row.get("metric") or "").strip() in {"temperature", "flow"}
            and str(row.get("sensor_name") or "").strip()
            not in {"gc_temp_salon", "gc_temp_etage", "weather_outdoor"}
        }
    )

    all_ready = all(result["ready"] for result in role_results.values())
    configured_count = sum(
        1 for result in role_results.values() if result["state"] != "UNSET"
    )

    if not hydraulic_candidates:
        upstream_state = "UPSTREAM_EMPTY"
    else:
        upstream_state = "OBSERVED"

    return {
        "component": "geocooling_telemetry_health",
        "ready": all_ready,
        "fail_closed": not all_ready,
        "stale_seconds": threshold,
        "upstream_state": upstream_state,
        "observed_sensor_count": len(observed_sensors),
        "hydraulic_candidate_count": len(hydraulic_candidates),
        "configured_role_count": configured_count,
        "roles": role_results,
    }
