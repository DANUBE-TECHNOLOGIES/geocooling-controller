from datetime import datetime, timedelta, timezone

from app.geocooling.telemetry_health import (
    build_telemetry_health,
    classify_role,
)


NOW = datetime(2026, 8, 9, 18, 30, tzinfo=timezone.utc)


def row(sensor, metric="temperature", age=10, value=18.2):
    return {
        "sensor_name": sensor,
        "metric": metric,
        "value": value,
        "unit": "°C" if metric == "temperature" else "l/min",
        "mqtt_topic": f"geocooling/{sensor}/{metric}",
        "measured_at": (NOW - timedelta(seconds=age)).isoformat(),
    }


def test_unset_role_is_fail_closed():
    result = classify_role(
        role="surface",
        sensor_name=None,
        metric="temperature",
        rows=[],
        now=NOW,
        env_var="GEOCOOLING_SURFACE_SENSOR",
    )
    assert result["state"] == "UNSET"
    assert result["ready"] is False
    assert result["env_var"] == "GEOCOOLING_SURFACE_SENSOR"


def test_configured_but_never_observed_is_source_absent():
    result = classify_role(
        role="surface",
        sensor_name="gc_surface",
        metric="temperature",
        rows=[row("gc_temp_salon")],
        now=NOW,
    )
    assert result["state"] == "SOURCE_ABSENT"


def test_observed_sensor_without_required_metric_is_metric_absent():
    result = classify_role(
        role="flow",
        sensor_name="gc_flow",
        metric="flow",
        rows=[row("gc_flow", metric="temperature")],
        now=NOW,
    )
    assert result["state"] == "METRIC_ABSENT"


def test_stale_metric_is_rejected():
    result = classify_role(
        role="floor_supply",
        sensor_name="gc_floor_supply",
        metric="temperature",
        rows=[row("gc_floor_supply", age=121)],
        stale_seconds=120,
        now=NOW,
    )
    assert result["state"] == "STALE"
    assert result["age_seconds"] == 121.0


def test_fresh_metric_is_ok():
    result = classify_role(
        role="source_inlet",
        sensor_name="gc_source_in",
        metric="temperature",
        rows=[row("gc_source_in", age=15, value=12.4)],
        now=NOW,
    )
    assert result["state"] == "OK"
    assert result["ready"] is True
    assert result["value"] == 12.4


def test_current_site_observation_is_reported_upstream_empty():
    rows = [
        row("gc_temp_salon", value=26.4),
        row("gc_temp_etage", value=29.1),
        row("weather_outdoor", value=31.8),
    ]
    mappings = {
        "surface": None,
        "floor_supply": None,
        "floor_return": None,
        "source_inlet": None,
        "source_outlet": None,
        "flow": None,
    }
    result = build_telemetry_health(
        rows,
        mappings=mappings,
        now=NOW,
    )
    assert result["upstream_state"] == "UPSTREAM_EMPTY"
    assert result["ready"] is False
    assert result["fail_closed"] is True
    assert result["hydraulic_candidate_count"] == 0
    assert result["candidate_sensors"] == []
    assert result["auto_assignment_allowed"] is False
    assert result["physical_confirmation_required"] is True


def test_candidates_are_exposed_without_role_assignment():
    rows = [
        row("probe_a", value=18.1),
        row("probe_b", value=20.2),
        row("flow_meter", metric="flow", value=28.0),
        row("gc_temp_salon", value=26.4),
    ]
    result = build_telemetry_health(rows, mappings={}, now=NOW)

    assert result["upstream_state"] == "OBSERVED"
    assert result["hydraulic_candidate_count"] == 3
    assert result["candidate_sensors"] == [
        {
            "sensor_name": "flow_meter",
            "metrics": ["flow"],
            "mqtt_topics": ["geocooling/flow_meter/flow"],
        },
        {
            "sensor_name": "probe_a",
            "metrics": ["temperature"],
            "mqtt_topics": ["geocooling/probe_a/temperature"],
        },
        {
            "sensor_name": "probe_b",
            "metrics": ["temperature"],
            "mqtt_topics": ["geocooling/probe_b/temperature"],
        },
    ]
    assert all(role["state"] == "UNSET" for role in result["roles"].values())


def test_installed_four_sensor_profile_is_ready_with_derived_surface_and_optional_flow():
    mappings = {
        "surface": None,
        "floor_supply": "gc_floor_supply",
        "floor_return": "gc_floor_return",
        "source_inlet": "gc_source_inlet",
        "source_outlet": "gc_source_outlet",
        "flow": None,
    }
    rows = [
        row("gc_floor_supply", value=18.0),
        row("gc_floor_return", value=20.0),
        row("gc_source_inlet", value=12.0),
        row("gc_source_outlet", value=14.0),
    ]

    result = build_telemetry_health(
        rows,
        mappings=mappings,
        now=NOW,
        surface_reference_mode="floor_loop_estimate",
        flow_required=False,
    )

    assert result["ready"] is True
    assert result["required_role_count"] == 5
    assert result["optional_roles"] == ["flow"]
    assert result["roles"]["surface"]["state"] == "DERIVED_OK"
    assert result["roles"]["surface"]["value"] == 18.5
    assert result["roles"]["flow"]["required_for_operation"] is False


def test_surface_estimate_fails_closed_when_one_floor_probe_is_stale():
    mappings = {
        "surface": None,
        "floor_supply": "gc_floor_supply",
        "floor_return": "gc_floor_return",
        "source_inlet": "gc_source_inlet",
        "source_outlet": "gc_source_outlet",
        "flow": None,
    }
    rows = [
        row("gc_floor_supply", value=18.0),
        row("gc_floor_return", age=121, value=20.0),
        row("gc_source_inlet", value=12.0),
        row("gc_source_outlet", value=14.0),
    ]

    result = build_telemetry_health(
        rows,
        mappings=mappings,
        stale_seconds=120,
        now=NOW,
        surface_reference_mode="floor_loop_estimate",
    )

    assert result["ready"] is False
    assert result["roles"]["surface"]["state"] == "DERIVED_UNAVAILABLE"


def test_all_six_roles_can_be_ready_with_real_surface_and_flow():
    mappings = {
        "surface": "gc_surface",
        "floor_supply": "gc_floor_supply",
        "floor_return": "gc_floor_return",
        "source_inlet": "gc_source_in",
        "source_outlet": "gc_source_out",
        "flow": "gc_flow",
    }
    rows = [
        row("gc_surface"),
        row("gc_floor_supply"),
        row("gc_floor_return"),
        row("gc_source_in"),
        row("gc_source_out"),
        row("gc_flow", metric="flow", value=28.0),
    ]
    result = build_telemetry_health(
        rows,
        mappings=mappings,
        now=NOW,
        surface_reference_mode="sensor",
        flow_required=True,
    )
    assert result["upstream_state"] == "OBSERVED"
    assert result["ready"] is True
    assert all(item["state"] == "OK" for item in result["roles"].values())
    assert result["roles"]["surface"]["env_var"] == "GEOCOOLING_SURFACE_SENSOR"
    assert result["roles"]["flow"]["env_var"] == "GEOCOOLING_FLOW_SENSOR"
