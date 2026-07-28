import json

from app.geocooling.industrial_platform import GeoCoolingEventJournal
from app.geocooling.operational_continuity import GeoCoolingOperationalContinuityManager


def _manager(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    return GeoCoolingOperationalContinuityManager(journal, path=str(tmp_path / "continuity.json"))


def _inputs():
    return {
        "availability": {"availability": "AVAILABLE", "availability_score": 95, "recovery_required": False, "automatic_mode_allowed": True},
        "confidence": {"confidence_level": "HIGH", "confidence_score": 95, "automatic_mode_allowed": True},
        "safety": {"safe": True, "emergency_stop": False},
        "hardware": {"armed": False, "pump_running": False, "valve_open": False},
    }


def test_first_boot_continuity_ready(tmp_path):
    manager = _manager(tmp_path)
    report = manager.evaluate(**_inputs())
    assert report["restart_detected"] is False
    assert report["continuity_state"] == "READY"
    assert report["automatic_mode_allowed"] is True
    assert report["physical_activation_allowed"] is False


def test_restart_requires_controlled_recovery(tmp_path):
    first = _manager(tmp_path)
    first.evaluate(**_inputs())
    second = _manager(tmp_path)
    report = second.evaluate(**_inputs())
    assert report["restart_detected"] is True
    assert report["continuity_state"] == "RECOVERY_REQUIRED"
    assert "validate-post-restart-baseline" in report["recovery_steps"]
    assert report["automatic_mode_allowed"] is False


def test_corrupt_state_blocks_continuity(tmp_path):
    manager = _manager(tmp_path)
    manager.evaluate(**_inputs())
    payload = json.loads(manager.path.read_text())
    payload["checksum"] = "invalid"
    manager.path.write_text(json.dumps(payload))
    restarted = _manager(tmp_path)
    report = restarted.evaluate(**_inputs())
    assert report["persisted_state_integrity"] == "FAIL"
    assert report["continuity_state"] == "BLOCKED"
    assert "persisted-state-integrity-failed" in report["inconsistencies"]


def test_unsafe_outputs_block_continuity(tmp_path):
    manager = _manager(tmp_path)
    inputs = _inputs()
    inputs["hardware"] = {"armed": False, "pump_running": True, "valve_open": False}
    report = manager.evaluate(**inputs)
    assert report["continuity_state"] == "BLOCKED"
    assert "outputs-not-in-safe-state" in report["inconsistencies"]
    assert report["hardware_touched"] is False
