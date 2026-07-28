from app.geocooling.data_quality import GeoCoolingSensorQualityManager
from app.geocooling.industrial_platform import GeoCoolingEventJournal
from app.geocooling.brain_v4 import GeoCoolingBrainV4
from app.geocooling.operational_advisory import GeoCoolingTelemetryHub


def test_quality_detects_out_of_range_value(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingSensorQualityManager(journal, path=str(tmp_path / "quality.json"))
    report = manager.assess({"indoor_temperature_c": 75})
    assert report["status"] == "FAIL"
    assert report["failures"][0]["sensor"] == "indoor_temperature_c"
    assert report["hardware_touched"] is False


def test_calibration_is_applied_to_ingested_telemetry(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingSensorQualityManager(journal, path=str(tmp_path / "quality.json"))
    manager.set_calibration("indoor_temperature_c", offset=-0.4, operator="tester")
    brain = GeoCoolingBrainV4(path=str(tmp_path / "brain.json"))
    hub = GeoCoolingTelemetryHub(brain, journal, path=str(tmp_path / "telemetry.json"), quality_manager=manager)
    result = hub.ingest({"indoor_temperature_c": 25.0})
    assert result["observation"]["indoor_temperature_c"] == 24.6
    assert result["data_quality"]["physical_activation_allowed"] is False


def test_calibration_offset_is_bounded(tmp_path):
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    manager = GeoCoolingSensorQualityManager(journal, path=str(tmp_path / "quality.json"))
    try:
        manager.set_calibration("indoor_temperature_c", offset=9, operator="tester")
    except ValueError as exc:
        assert "between -5.0 and +5.0" in str(exc)
    else:
        raise AssertionError("Expected ValueError")
