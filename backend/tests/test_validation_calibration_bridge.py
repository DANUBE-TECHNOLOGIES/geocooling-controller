from app.geocooling.rc3.validation_calibration_bridge import (
    ValidationCalibrationBridge,
)


def test_match_conversion():
    sample = ValidationCalibrationBridge.sample_from_match(
        {
            "horizon_minutes": 60,
            "predicted_indoor_temperature_c": 25.5,
            "actual_indoor_temperature_c": 25.2,
        }
    )

    assert sample is not None
    assert sample.horizon_minutes == 60
    assert round(sample.error_c, 4) == 0.3
