import pytest

from app.geocooling.physical_thermal_model import GeoCoolingPhysicalThermalModel


def test_status_is_advisory_and_disarmed():
    report = GeoCoolingPhysicalThermalModel().status()
    assert report["advisory_only"] is True
    assert report["physical_activation_allowed"] is False
    assert report["parameters"]["floor_area_m2"] > 0


def test_condensation_envelope_requires_humidity():
    report = GeoCoolingPhysicalThermalModel().condensation_envelope(26, None)
    assert report["available"] is False
    assert report["minimum_safe_supply_c"] is None


def test_active_prediction_cools_more_than_passive():
    model = GeoCoolingPhysicalThermalModel()
    common = {
        "indoor_temperature_c": 27,
        "outdoor_temperature_c": 30,
        "humidity_percent": 50,
        "target_temperature_c": 24,
        "hours": 2,
        "solar_factor": 0.5,
    }
    passive = model.predict({**common, "cooling_enabled": False})
    active = model.predict({**common, "cooling_enabled": True})
    assert active["prediction"]["final_temperature_c"] < passive["prediction"]["final_temperature_c"]
    assert active["prediction"]["recommended_runtime_minutes"] > 0
    assert active["physical_activation_allowed"] is False


def test_optimizer_blocks_without_condensation_data():
    model = GeoCoolingPhysicalThermalModel()
    result = model.optimize({
        "indoor_temperature_c": 27,
        "outdoor_temperature_c": 30,
        "target_temperature_c": 24,
        "hours": 2,
    })
    assert result["optimization"]["recommended_action"] == "WAIT"
    assert result["prediction"]["condensation_interlock"] is True
    assert result["optimization"]["hardware_touched"] is False


def test_missing_required_temperature_is_rejected():
    with pytest.raises(ValueError):
        GeoCoolingPhysicalThermalModel().predict({"indoor_temperature_c": 25})
