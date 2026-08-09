from app.geocooling.rc3.predictor_calibration import (
    CalibrationSample,
    PredictorCalibrationEngine,
)


def test_calibration_requires_enough_samples() -> None:
    report = PredictorCalibrationEngine(
        minimum_samples=5,
    ).calibrate(
        current_model={
            "fast_time_constant_hours": 2.5,
            "slow_time_constant_hours": 18.0,
            "mass_coupling": 0.28,
            "solar_gain_c_per_hour_at_full_sun": 0.20,
            "soft_cooling_c_per_hour": 0.28,
            "full_cooling_c_per_hour": 0.52,
            "model_confidence": 0.62,
        },
        samples=(
            CalibrationSample(
                horizon_minutes=60,
                predicted_c=25.5,
                actual_c=25.0,
                error_c=0.5,
            ),
        ),
    )

    assert report["status"] == "INSUFFICIENT_DATA"
    assert report["activation"]["automatic"] is False


def test_calibration_produces_reviewable_proposal() -> None:
    samples = tuple(
        CalibrationSample(
            horizon_minutes=60 if index < 8 else 720,
            predicted_c=25.4,
            actual_c=25.0,
            error_c=0.4,
        )
        for index in range(16)
    )

    report = PredictorCalibrationEngine(
        minimum_samples=12,
    ).calibrate(
        current_model={
            "fast_time_constant_hours": 2.5,
            "slow_time_constant_hours": 18.0,
            "mass_coupling": 0.28,
            "solar_gain_c_per_hour_at_full_sun": 0.20,
            "soft_cooling_c_per_hour": 0.28,
            "full_cooling_c_per_hour": 0.52,
            "model_confidence": 0.62,
        },
        samples=samples,
    )

    assert report["status"] == "PROPOSAL_READY"
    assert report["activation"]["automatic"] is False
    assert report["safety"]["controller_authorized"] is False
