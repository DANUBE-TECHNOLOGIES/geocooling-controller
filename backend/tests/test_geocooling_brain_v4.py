from app.geocooling.brain_v4 import GeoCoolingBrainV4, dew_point_c


def test_dew_point_is_physically_plausible():
    value = dew_point_c(26.0, 60.0)
    assert 17.0 < value < 19.0


def test_brain_v4_blocks_when_condensation_inputs_are_missing(tmp_path):
    brain = GeoCoolingBrainV4(path=str(tmp_path / "model.json"))
    result = brain.analyze({"latest": {"indoor_temperature_c": 26.0}}, {"safe": True})
    assert result["recommended_action"] == "WAIT"
    assert "humidity-missing" in result["blocking_conditions"]
    assert result["physical_command_authorized"] is False


def test_brain_v4_recommends_predictive_cooling_when_safe(tmp_path):
    brain = GeoCoolingBrainV4(path=str(tmp_path / "model.json"))
    result = brain.analyze({"latest": {
        "indoor_temperature_c": 26.0,
        "indoor_humidity_percent": 50.0,
        "supply_temperature_c": 19.0,
        "floor_surface_temperature_c": 21.0,
        "outdoor_temperature_c": 31.0,
    }}, {"safe": True})
    assert result["recommended_action"] == "COOL"
    assert result["recommended_runtime_minutes"] >= 15
    assert result["condensation_safe"] is True
    assert result["physical_command_authorized"] is False


def test_brain_v4_learns_active_and_passive_rates(tmp_path):
    brain = GeoCoolingBrainV4(path=str(tmp_path / "model.json"))
    passive = brain.observe(
        {"timestamp": "2026-07-28T10:00:00+00:00", "indoor_temperature_c": 25.0, "pump_running": False},
        {"timestamp": "2026-07-28T11:00:00+00:00", "indoor_temperature_c": 25.3, "pump_running": False},
    )
    active = brain.observe(
        {"timestamp": "2026-07-28T11:00:00+00:00", "indoor_temperature_c": 25.3, "pump_running": True},
        {"timestamp": "2026-07-28T12:00:00+00:00", "indoor_temperature_c": 24.9, "pump_running": True},
    )
    assert passive["accepted"] is True
    assert active["accepted"] is True
    model = brain.model_status()
    assert model["passive_samples"] == 1
    assert model["active_samples"] == 1


def test_weather_update_is_persistent(tmp_path):
    path = tmp_path / "model.json"
    brain = GeoCoolingBrainV4(path=str(path))
    brain.update_weather({"forecast_max_6h_c": 34, "source": "home-assistant"})
    reloaded = GeoCoolingBrainV4(path=str(path))
    assert reloaded.model_status()["weather"]["forecast_max_6h_c"] == 34.0
