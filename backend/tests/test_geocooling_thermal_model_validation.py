import pytest

from app.geocooling.physical_thermal_model import GeoCoolingPhysicalThermalModel
from app.geocooling.thermal_model_learning import GeoCoolingThermalModelLearning
from app.geocooling.thermal_model_validation import GeoCoolingThermalModelValidation


def manager(tmp_path):
    model = GeoCoolingPhysicalThermalModel()
    learner = GeoCoolingThermalModelLearning(model, str(tmp_path / "learning.json"))
    item = GeoCoolingThermalModelValidation(model, learner, str(tmp_path / "validation.json"))
    item.minimum_scenarios = 4
    item.minimum_improvement_percent = 1
    return item


def scenarios_for(item, candidate):
    item.learner.adjustments = candidate
    scenarios = []
    for indoor in (26.0, 26.5, 27.0, 27.5, 28.0, 28.5):
        payload = {
            "indoor_temperature_c": indoor,
            "outdoor_temperature_c": 31,
            "humidity_percent": 50,
            "hours": 1,
            "cooling_enabled": True,
            "solar_factor": 0.4,
        }
        observed = item._predict_with(payload, candidate)
        scenarios.append({**payload, "observed_temperature_c": observed})
    return scenarios


def test_status_is_advisory_and_disarmed(tmp_path):
    status = manager(tmp_path).status()
    assert status["physical_activation_allowed"] is False
    assert status["hardware_touched"] is False


def test_evaluation_rejects_too_few_scenarios(tmp_path):
    with pytest.raises(ValueError):
        manager(tmp_path).evaluate({"scenarios": []})


def test_candidate_can_be_cross_validated_and_promoted(tmp_path):
    item = manager(tmp_path)
    candidate = {"heat_capacity_factor": 1.2, "cooling_power_factor": 0.8}
    result = item.evaluate({"scenarios": scenarios_for(item, candidate)})
    assert result["promotable"] is True
    promoted = item.promote()
    assert promoted["promoted"] is True
    assert promoted["physical_activation_allowed"] is False
    assert item.promoted_adjustments == candidate


def test_promotion_requires_successful_evaluation(tmp_path):
    with pytest.raises(ValueError):
        manager(tmp_path).promote()


def test_rollback_restores_previous_parameters(tmp_path):
    item = manager(tmp_path)
    candidate = {"heat_capacity_factor": 1.15, "cooling_power_factor": 0.85}
    item.evaluate({"scenarios": scenarios_for(item, candidate)})
    item.promote()
    result = item.rollback()
    assert result["rolled_back"] is True
    assert item.promoted_adjustments == {"heat_capacity_factor": 1.0, "cooling_power_factor": 1.0}


def test_promoted_prediction_never_touches_hardware(tmp_path):
    item = manager(tmp_path)
    result = item.predict({
        "indoor_temperature_c": 27,
        "outdoor_temperature_c": 30,
        "humidity_percent": 50,
        "hours": 1,
        "cooling_enabled": True,
    })
    assert result["hardware_touched"] is False
    assert result["physical_activation_allowed"] is False
