from app.geocooling.rc3.prediction_validation import (
    PredictionValidationEngine,
)


def snapshot(captured_at, indoor, predicted=None):
    payload = {
        "captured_at": captured_at,
        "context": {
            "measurements": {
                "indoor_temperature_c": indoor,
            }
        },
        "prediction": {
            "trajectories": [],
        },
    }

    if predicted is not None:
        payload["prediction"]["trajectories"] = [
            {
                "scenario": "BASELINE",
                "points": [
                    {
                        "horizon_minutes": 60,
                        "predicted_indoor_temperature_c": predicted,
                    }
                ],
            }
        ]

    return payload


def test_validation_matches_future_measurement() -> None:
    report = PredictionValidationEngine(
        tolerance_minutes=5,
    ).validate(
        [
            snapshot(
                "2026-08-03T12:00:00+00:00",
                25.0,
                25.6,
            ),
            snapshot(
                "2026-08-03T13:00:00+00:00",
                25.4,
            ),
        ]
    )

    assert report["match_count"] == 1
    assert report["metrics"]["mae_c"] == 0.2
    assert report["safety"]["controller_authorized"] is False
