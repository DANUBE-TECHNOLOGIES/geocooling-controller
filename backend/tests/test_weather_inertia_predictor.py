from app.geocooling.rc3.weather_inertia_predictor import (
    ThermalModelParameters,
    WeatherInertiaPredictor,
)


def sample_context():
    return {
        "measurements": {
            "indoor_temperature_c": 25.0,
            "outdoor_temperature_c": 30.0,
            "floor_surface_temperature_c": 23.0,
        }
    }


def sample_weather():
    return {
        "hourly": {
            "temperature_2m": [30 + index * 0.05 for index in range(49)],
            "cloud_cover": [20 for _ in range(49)],
            "shortwave_radiation": [600 for _ in range(49)],
        }
    }


def test_predictor_outputs_long_horizons() -> None:
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather=sample_weather(),
    )

    assert payload["horizons_minutes"][-1] == 2880
    assert len(payload["trajectories"]) == 3
    assert all(
        len(item["points"]) == 8
        for item in payload["trajectories"]
    )


def test_cooling_trajectory_is_below_baseline() -> None:
    payload = WeatherInertiaPredictor(
        ThermalModelParameters(
            model_confidence=0.8,
        )
    ).predict(
        context=sample_context(),
        weather=sample_weather(),
    )

    trajectories = {
        item["scenario"]: item["points"]
        for item in payload["trajectories"]
    }

    assert (
        trajectories["FULL_COOLING"][-1][
            "predicted_indoor_temperature_c"
        ]
        < trajectories["BASELINE"][-1][
            "predicted_indoor_temperature_c"
        ]
    )


def test_predictor_never_authorizes_controller() -> None:
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather=sample_weather(),
    )

    assert payload["safety"]["controller_authorized"] is False
    assert payload["safety"]["hardware_write"] is False
