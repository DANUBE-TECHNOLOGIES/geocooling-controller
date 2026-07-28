from app.geocooling.industrial_platform import GeoCoolingEventJournal
from app.geocooling.operational_availability import GeoCoolingOperationalAvailabilityManager


def _manager(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    return GeoCoolingOperationalAvailabilityManager(journal, path=str(tmp_path / "availability.json"))


def test_available_when_inputs_are_healthy(tmp_path):
    manager = _manager(tmp_path)
    report = manager.evaluate(
        confidence={"confidence_score": 95, "blocking_conditions": [], "automatic_mode_allowed": True},
        quality={"status": "PASS"},
        safety={"safe": True, "emergency_stop": False},
        hardware={"armed": False},
    )
    assert report["availability"] == "AVAILABLE"
    assert report["recovery_required"] is False
    assert report["hardware_touched"] is False


def test_persistent_anomaly_requires_recovery(tmp_path):
    manager = _manager(tmp_path)
    for _ in range(3):
        report = manager.evaluate(
            confidence={"confidence_score": 50, "blocking_conditions": ["stale-telemetry"], "automatic_mode_allowed": False},
            quality={"status": "PASS"},
            safety={"safe": True, "emergency_stop": False},
            hardware={"armed": False},
        )
    assert "stale-telemetry" in report["persistent_conditions"]
    assert report["availability"] == "UNAVAILABLE"
    assert report["recovery_required"] is True
    assert "restore-fresh-telemetry" in report["recovery_steps"]


def test_emergency_stop_forces_zero_availability(tmp_path):
    manager = _manager(tmp_path)
    report = manager.evaluate(
        confidence={"confidence_score": 100, "blocking_conditions": [], "automatic_mode_allowed": True},
        quality={"status": "PASS"},
        safety={"safe": False, "emergency_stop": True},
        hardware={"armed": False},
    )
    assert report["availability_score"] == 0
    assert report["automatic_mode_allowed"] is False
    assert report["physical_activation_allowed"] is False
