from app.geocooling.industrial_platform import (
    GeoCoolingBrainAdvisorV2,
    GeoCoolingEventJournal,
    GeoCoolingHardwareGateway,
    GeoCoolingIndustrialPlatform,
    GeoCoolingBrainAdvisorV3,
)


class FakeSafeMode:
    def status(self): return {"active": False}


class FakeHardening:
    safe_mode = FakeSafeMode()
    def startup_status(self): return {"status": "PASS"}
    def status(self): return {"startup_self_test": {"status": "PASS"}, "safe_mode": {"active": False}}


class FakeController:
    def brain_status(self): return {"decision": "WAIT", "confidence": 90, "recommended_runtime_minutes": 0}


def test_event_journal_and_metrics(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    journal.record("brain", "decision", message="wait")
    journal.record("hardware", "fault", level="ERROR", message="offline")
    metrics = journal.metrics()
    assert metrics["events"] == 2
    assert metrics["incidents"] == 1
    assert metrics["by_component"]["hardware"] == 1


def test_hardware_gateway_is_disarmed_and_dry_run_safe(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    gateway = GeoCoolingHardwareGateway(journal=journal)
    assert gateway.status()["armed"] is False
    result = gateway.dry_run("START_PUMP")
    assert result["accepted"] is True
    assert result["hardware_touched"] is False


def test_brain_v2_is_advisory_only():
    result = GeoCoolingBrainAdvisorV2().analyze({"decision": "START", "confidence": 88, "recommended_runtime_minutes": 20})
    assert result["advisory_only"] is True
    assert result["recommended_action"] == "START"


def test_platform_pre_certification_blocks_field_activation(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOCOOLING_EVENT_JOURNAL_PATH", str(tmp_path / "events.jsonl"))
    platform = GeoCoolingIndustrialPlatform(controller=FakeController(), hardening=FakeHardening())
    report = platform.certification()
    assert report["status"] == "PASS"
    assert report["field_activation_allowed"] is False
    assert report["requires_physical_waveshare_test"] is True
    assert platform.diagnostics()["healthy"] is True


def test_safety_manager_forces_safe_state_on_emergency(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOCOOLING_EVENT_JOURNAL_PATH", str(tmp_path / "events.jsonl"))
    platform = GeoCoolingIndustrialPlatform(controller=FakeController(), hardening=FakeHardening())
    result = platform.safety.emergency_stop("operator test", "tester")
    assert result["active"] is True
    assert platform.hardware.status()["armed"] is False
    assert platform.hardware.status()["pump_running"] is False
    assert platform.safety.evaluate({})["safe"] is False
    cleared = platform.safety.clear_emergency_stop("tester")
    assert cleared["hardware_remains_disarmed"] is True


def test_commissioning_is_persistent_dry_run_only(tmp_path, monkeypatch):
    monkeypatch.setenv("GEOCOOLING_EVENT_JOURNAL_PATH", str(tmp_path / "events.jsonl"))
    monkeypatch.setenv("GEOCOOLING_COMMISSIONING_PATH", str(tmp_path / "commissioning.json"))
    controller = FakeController()
    controller.thermal_status = lambda: {}
    platform = GeoCoolingIndustrialPlatform(controller=controller, hardening=FakeHardening())
    session = platform.commissioning.start("tester")
    for _ in platform.commissioning.STEPS:
        session = platform.commissioning.advance(session["session_id"])
    assert session["status"] == "SOFTWARE_COMPLETE_HARDWARE_PENDING"
    assert session["hardware_remains_disarmed"] is True
    assert platform.hardware.status()["armed"] is False
    assert all(not item["result"].get("hardware_touched", False) for item in session["results"])


def test_brain_v3_never_authorizes_physical_command():
    result = GeoCoolingBrainAdvisorV3().analyze(
        {"decision": "START", "confidence": 90, "recommended_runtime_minutes": 15},
        {"latest": {"indoor_temperature_c": 26.0, "supply_temperature_c": 18.0, "return_temperature_c": 20.0}},
        {"safe": True},
    )
    assert result["recommended_action"] == "START"
    assert result["physical_command_authorized"] is False
    assert result["learning_mode"] == "OBSERVE_ONLY"
