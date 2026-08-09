from __future__ import annotations

from datetime import datetime, timezone

from app.geocooling.telemetry_health_service import TelemetryHealthService


def test_health_is_read_only_and_delegates_role_classification(monkeypatch) -> None:
    service = TelemetryHealthService(database_url="sqlite://")
    now = datetime.now(timezone.utc).isoformat()

    monkeypatch.setattr(
        service,
        "latest_rows",
        lambda: [
            {
                "sensor_name": "floor_surface_probe",
                "metric": "temperature",
                "value": 21.4,
                "unit": "°C",
                "measured_at": now,
                "mqtt_topic": "esphome/floor_surface_probe",
            }
        ],
    )
    monkeypatch.setenv("GEOCOOLING_SURFACE_SENSOR", "floor_surface_probe")
    monkeypatch.delenv("GEOCOOLING_FLOOR_SUPPLY_SENSOR", raising=False)
    monkeypatch.delenv("GEOCOOLING_FLOOR_RETURN_SENSOR", raising=False)
    monkeypatch.delenv("GEOCOOLING_SOURCE_INLET_SENSOR", raising=False)
    monkeypatch.delenv("GEOCOOLING_SOURCE_OUTLET_SENSOR", raising=False)
    monkeypatch.delenv("GEOCOOLING_FLOW_SENSOR", raising=False)

    report = service.health()

    assert report["read_only"] is True
    assert report["hardware_touched"] is False
    assert report["mqtt_publish"] is False
    assert report["database_write"] is False
    assert report["roles"]["surface"]["state"] == "OK"
    assert report["roles"]["floor_supply"]["state"] == "UNSET"
    assert report["ready"] is False
    assert report["fail_closed"] is True
