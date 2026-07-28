from app.geocooling.industrial_platform import (
    GeoCoolingBrainAdvisorV2,
    GeoCoolingEventJournal,
    GeoCoolingHardwareGateway,
    GeoCoolingIndustrialPlatform,
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
