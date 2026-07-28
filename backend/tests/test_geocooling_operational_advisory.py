from app.geocooling.brain_v4 import GeoCoolingBrainV4
from app.geocooling.industrial_platform import GeoCoolingEventJournal
from app.geocooling.operational_advisory import GeoCoolingTelemetryHub


def test_telemetry_normalizes_home_assistant_aliases(tmp_path):
    brain = GeoCoolingBrainV4(path=str(tmp_path / "brain.json"))
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    hub = GeoCoolingTelemetryHub(brain, journal, path=str(tmp_path / "telemetry.json"))
    result = hub.ingest({
        "timestamp": "2026-07-28T10:00:00+00:00",
        "source": "home-assistant",
        "state": {
            "indoor_temperature": 25.2,
            "humidity_percent": 55,
            "depart_temperature_c": 18.5,
            "debit_l_min": 22,
            "pump": False,
        },
    })
    observation = result["observation"]
    assert observation["indoor_temperature_c"] == 25.2
    assert observation["indoor_humidity_percent"] == 55.0
    assert observation["supply_temperature_c"] == 18.5
    assert observation["flow_l_min"] == 22.0
    assert result["hardware_touched"] is False


def test_second_telemetry_sample_feeds_brain_learning(tmp_path):
    brain = GeoCoolingBrainV4(path=str(tmp_path / "brain.json"))
    journal = GeoCoolingEventJournal(path=str(tmp_path / "events.jsonl"))
    hub = GeoCoolingTelemetryHub(brain, journal, path=str(tmp_path / "telemetry.json"))
    hub.ingest({"timestamp": "2026-07-28T10:00:00+00:00", "indoor_temperature_c": 25.0, "pump_running": False})
    result = hub.ingest({"timestamp": "2026-07-28T11:00:00+00:00", "indoor_temperature_c": 25.3, "pump_running": False})
    assert result["learning"]["accepted"] is True
    assert brain.model_status()["passive_samples"] == 1
