from datetime import datetime, timedelta, timezone

from app.geocooling.industrial_platform import GeoCoolingEventJournal
from app.geocooling.operational_confidence import GeoCoolingOperationalConfidenceManager


def _complete_observation(timestamp: str) -> dict:
    return {
        "timestamp": timestamp,
        "indoor_temperature_c": 24.0,
        "indoor_humidity_percent": 50.0,
        "supply_temperature_c": 18.0,
        "return_temperature_c": 20.0,
        "source_in_temperature_c": 12.0,
        "source_out_temperature_c": 15.0,
        "flow_l_min": 22.0,
    }


def test_operational_confidence_high_for_fresh_complete_data(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingOperationalConfidenceManager(journal, path=str(tmp_path / "confidence.json"))
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    latest = _complete_observation((now - timedelta(seconds=30)).isoformat())
    previous = _complete_observation((now - timedelta(minutes=30)).isoformat())
    report = manager.evaluate(latest=latest, previous=previous, quality={"status": "PASS"}, physical_mode=True, now=now)
    assert report["confidence_level"] == "HIGH"
    assert report["automatic_mode_allowed"] is True
    assert report["hardware_touched"] is False


def test_stale_telemetry_forces_software_interlock(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingOperationalConfidenceManager(journal, path=str(tmp_path / "confidence.json"))
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    latest = _complete_observation((now - timedelta(minutes=20)).isoformat())
    report = manager.evaluate(latest=latest, previous=None, quality={"status": "PASS"}, physical_mode=True, now=now)
    assert "stale-telemetry" in report["blocking_conditions"]
    assert report["software_interlock_required"] is True
    assert report["automatic_mode_allowed"] is False


def test_sensor_drift_is_detected(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingOperationalConfidenceManager(journal, path=str(tmp_path / "confidence.json"))
    now = datetime(2026, 7, 28, 12, 0, tzinfo=timezone.utc)
    previous = _complete_observation((now - timedelta(minutes=10)).isoformat())
    latest = _complete_observation(now.isoformat())
    latest["indoor_temperature_c"] = 30.0
    report = manager.evaluate(latest=latest, previous=previous, quality={"status": "PASS"}, physical_mode=False, now=now)
    assert "sensor-drift-detected" in report["blocking_conditions"]
    assert any(item["sensor"] == "indoor_temperature_c" for item in report["drift_failures"])
    assert report["physical_activation_allowed"] is False
