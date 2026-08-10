"""GeoCooling telemetry-role health classification.

Pure read-only helpers used to distinguish configuration errors from upstream
sensor/metric loss. This module never publishes messages and never commands any
actuator.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any, Mapping, Sequence

from app.geocooling.surface_estimation import estimate_floor_surface_temperature


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

NON_HYDRAULIC_SENSORS = {
    "gc_temp_salon",
    "gc_temp_etage",
    "weather_outdoor",
}


def _bool_env(name: str, default: bool = False) -> bool:
    raw = os.getenv(name)
    if raw is None:
        return default
    return raw.strip().lower() in {"1", "true", "yes", "on"}


def _surface_reference_mode(value: str | None = None) -> str:
    mode = (value or os.getenv("GEOCOOLING_SURFACE_REFERENCE_MODE", "sensor")).strip().lower()
    if mode == "floor_supply_proxy":
        return "floor_loop_estimate"
    if mode not in {"sensor", "floor_loop_estimate"}:
        return "sensor"
    return mode


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
    env_var: str | None = None,
) -> dict[str, Any]:
    """Classify one role as UNSET/SOURCE_ABSENT/METRIC_ABSENT/STALE/OK."""

    current_time = (now or datetime.now(timezone.utc)).astimezone(timezone.utc)
    configured_sensor = (sensor_name or "").strip()

    base = {
        "role": role,
        "env_var": env_var,
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


def _candidate_sensors(
    rows: Sequence[Mapping[str, Any]],
) -> list[dict[str, Any]]:
    """Return observed hydraulic candidates without assigning a physical role."""

    candidates: dict[str, dict[str, Any]] = {}

    for row in rows:
        sensor_name = str(row.get("sensor_name") or "").strip()
        metric = str(row.get("metric") or "").strip()

        if (
            not sensor_name
            or sensor_name in NON_HYDRAULIC_SENSORS
            or metric not in {"temperature", "flow"}
        ):
            continue

        item = candidates.setdefault(
            sensor_name,
            {
                "sensor_name": sensor_name,
                "metrics": set(),
                "mqtt_topics": set(),
            },
        )
        item["metrics"].add(metric)
        topic = str(row.get("mqtt_topic") or "").strip()
        if topic:
            item["mqtt_topics"].add(topic)

    return [
        {
            "sensor_name": item["sensor_name"],
            "metrics": sorted(item["metrics"]),
            "mqtt_topics": sorted(item["mqtt_topics"]),
        }
        for item in sorted(
            candidates.values(),
            key=lambda value: value["sensor_name"],
        )
    ]


def build_telemetry_health(
    rows: Sequence[Mapping[str, Any]],
    *,
    mappings: Mapping[str, str | None] | None = None,
    stale_seconds: int | None = None,
    now: datetime | None = None,
    surface_reference_mode: str | None = None,
    flow_required: bool | None = None,
) -> dict[str, Any]:
    """Build a fail-closed health report for the installed GeoCooling profile.

    The four hydraulic temperatures are always required. Flow is optional by
    default because it is used for power/energy metering, not condensation
    safety. Surface protection can use either a real sensor or an explicitly
    enabled conservative estimate derived from floor supply + return.
    """

    threshold = int(
        stale_seconds
        if stale_seconds is not None
        else os.getenv("GEOCOOLING_SENSOR_STALE_SECONDS", "120")
    )
    supplied = mappings or {}
    reference_mode = _surface_reference_mode(surface_reference_mode)
    require_flow = (
        _bool_env("GEOCOOLING_FLOW_REQUIRED", False)
        if flow_required is None
        else bool(flow_required)
    )

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
            env_var=spec["env"],
        )

    if reference_mode == "floor_loop_estimate":
        supply = role_results["floor_supply"]
        return_ = role_results["floor_return"]
        both_ready = bool(supply.get("ready") and return_.get("ready"))
        estimate = estimate_floor_surface_temperature(
            supply.get("value") if both_ready else None,
            return_.get("value") if both_ready else None,
        )
        ages = [
            item.get("age_seconds")
            for item in (supply, return_)
            if item.get("age_seconds") is not None
        ]
        measured_times = [
            item.get("measured_at")
            for item in (supply, return_)
            if item.get("measured_at")
        ]
        role_results["surface"] = {
            "role": "surface",
            "env_var": "GEOCOOLING_SURFACE_REFERENCE_MODE",
            "sensor_name": "derived:gc_floor_supply+gc_floor_return",
            "metric": "temperature",
            "stale_seconds": threshold,
            "measured_at": min(measured_times) if measured_times else None,
            "age_seconds": max(ages) if ages else None,
            "value": estimate.temperature_c,
            "unit": "°C",
            "mqtt_topic": None,
            "state": "DERIVED_OK" if both_ready and estimate.available else "DERIVED_UNAVAILABLE",
            "ready": bool(both_ready and estimate.available),
            "derived": True,
            "derivation": estimate.as_dict(),
            "reason": (
                "Conservative floor-surface reference derived from fresh floor supply and return temperatures."
                if both_ready and estimate.available
                else "Surface estimate unavailable because floor supply/return telemetry is incomplete or stale."
            ),
        }
    else:
        role_results["surface"]["derived"] = False

    for role, result in role_results.items():
        result["required_for_operation"] = role != "flow" or require_flow
        if role == "surface":
            result["required_for_operation"] = True

    required_roles = [
        role for role, result in role_results.items()
        if result["required_for_operation"]
    ]
    optional_roles = [
        role for role, result in role_results.items()
        if not result["required_for_operation"]
    ]

    required_ready = all(role_results[role]["ready"] for role in required_roles)
    configured_required_count = sum(
        1
        for role in required_roles
        if role_results[role]["state"] not in {"UNSET", "DERIVED_UNAVAILABLE"}
    )
    configured_count = sum(
        1 for result in role_results.values() if result["state"] != "UNSET"
    )

    observed_sensors = sorted(
        {
            str(row.get("sensor_name") or "").strip()
            for row in rows
            if str(row.get("sensor_name") or "").strip()
        }
    )
    candidates = _candidate_sensors(rows)
    upstream_state = "OBSERVED" if candidates else "UPSTREAM_EMPTY"

    return {
        "component": "geocooling_telemetry_health",
        "ready": required_ready,
        "fail_closed": not required_ready,
        "stale_seconds": threshold,
        "upstream_state": upstream_state,
        "observed_sensor_count": len(observed_sensors),
        "hydraulic_candidate_count": len(candidates),
        "configured_role_count": configured_count,
        "required_role_count": len(required_roles),
        "configured_required_role_count": configured_required_count,
        "optional_role_count": len(optional_roles),
        "required_roles": required_roles,
        "optional_roles": optional_roles,
        "surface_reference_mode": reference_mode,
        "flow_required": require_flow,
        "auto_assignment_allowed": False,
        "physical_confirmation_required": True,
        "candidate_sensors": candidates,
        "roles": role_results,
    }
