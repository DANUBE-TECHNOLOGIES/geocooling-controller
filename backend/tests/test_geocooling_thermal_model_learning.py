import pytest

from app.geocooling.physical_thermal_model import GeoCoolingPhysicalThermalModel
from app.geocooling.thermal_model_learning import GeoCoolingThermalModelLearning


def learner(tmp_path):
    item = GeoCoolingThermalModelLearning(GeoCoolingPhysicalThermalModel(), str(tmp_path / "learning.json"))
    item.minimum_samples = 3
    return item


def test_learning_starts_disarmed(tmp_path):
    status = learner(tmp_path).status()
    assert status["physical_activation_allowed"] is False
    assert status["metrics"]["sample_count"] == 0


def test_observation_updates_error_metrics(tmp_path):
    item = learner(tmp_path)
    result = item.observe({"predicted_temperature_c": 25, "observed_temperature_c": 25.5, "duration_minutes": 60, "cooling_enabled": False})
    assert result["accepted"] is True
    assert result["sample"]["error_c"] == 0.5
    assert result["hardware_touched"] is False


def test_adjustments_are_bounded(tmp_path):
    item = learner(tmp_path)
    for _ in range(80):
        item.observe({"predicted_temperature_c": 24, "observed_temperature_c": 30, "duration_minutes": 60, "cooling_enabled": True})
    assert 0.60 <= item.adjustments["cooling_power_factor"] <= 1.40
    assert item.status()["calibration_ready"] is True


def test_learned_prediction_restores_base_model(tmp_path):
    model = GeoCoolingPhysicalThermalModel()
    item = GeoCoolingThermalModelLearning(model, str(tmp_path / "learning.json"))
    item.adjustments["cooling_power_factor"] = 0.8
    base_power = model.nominal_cooling_kw
    result = item.predict({"indoor_temperature_c": 27, "outdoor_temperature_c": 30, "humidity_percent": 50, "hours": 1, "cooling_enabled": True})
    assert model.nominal_cooling_kw == base_power
    assert result["learning"]["physical_activation_allowed"] is False


def test_invalid_observation_is_rejected(tmp_path):
    with pytest.raises(ValueError):
        learner(tmp_path).observe({"predicted_temperature_c": 25})
