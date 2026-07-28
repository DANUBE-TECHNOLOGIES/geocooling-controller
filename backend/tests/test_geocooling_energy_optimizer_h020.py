import pytest

from app.geocooling.energy_optimizer import GeoCoolingEnergyOptimizer
from app.geocooling.physical_thermal_model import GeoCoolingPhysicalThermalModel
from app.geocooling.thermal_model_learning import GeoCoolingThermalModelLearning
from app.geocooling.thermal_model_validation import GeoCoolingThermalModelValidation


def optimizer(tmp_path):
    model = GeoCoolingPhysicalThermalModel()
    learner = GeoCoolingThermalModelLearning(model, str(tmp_path / "learning.json"))
    validation = GeoCoolingThermalModelValidation(model, learner, str(tmp_path / "validation.json"))
    return GeoCoolingEnergyOptimizer(model, validation, str(tmp_path / "energy.json"))


def forecast(hours=24):
    return [{"outdoor_temperature_c": 29 + (i % 6) * 0.5, "humidity_percent": 50, "solar_factor": 0.7 if 8 <= i <= 18 else 0.1} for i in range(hours)]


def test_status_is_advisory_only(tmp_path):
    result = optimizer(tmp_path).status()
    assert result["physical_activation_allowed"] is False
    assert result["hardware_touched"] is False


def test_forecast_is_required(tmp_path):
    with pytest.raises(ValueError):
        optimizer(tmp_path).optimize({"indoor_temperature_c": 27, "target_temperature_c": 24, "forecast": []})


def test_optimizer_returns_single_cycle_schedule(tmp_path):
    result = optimizer(tmp_path).optimize({"indoor_temperature_c": 27, "target_temperature_c": 24, "forecast": forecast()})
    assert len(result["schedule"]) == 24
    assert result["estimated_starts"] in (0, 1)
    assert result["recommended_runtime_minutes"] % 60 == 0
    assert result["physical_activation_allowed"] is False


def test_optimizer_prefers_hold_when_already_cool(tmp_path):
    result = optimizer(tmp_path).optimize({"indoor_temperature_c": 22, "target_temperature_c": 24, "forecast": [{"outdoor_temperature_c": 20, "humidity_percent": 50, "solar_factor": 0}] * 6})
    assert result["recommended_action"] == "HOLD"
    assert result["recommended_runtime_minutes"] == 0


def test_daily_assessment_is_persisted(tmp_path):
    item = optimizer(tmp_path)
    result = item.assess({"predicted_final_temperature_c": 24.5, "observed_final_temperature_c": 24.7, "planned_energy_kwh": 1.0, "actual_energy_kwh": 1.1, "target_temperature_c": 24.5})
    assert result["performance"] == "GOOD"
    assert len(item.assessments()) == 1
    restored = optimizer(tmp_path)
    assert len(restored.assessments()) == 1


def test_assessment_requires_complete_measurements(tmp_path):
    with pytest.raises(ValueError):
        optimizer(tmp_path).assess({"predicted_final_temperature_c": 24})
