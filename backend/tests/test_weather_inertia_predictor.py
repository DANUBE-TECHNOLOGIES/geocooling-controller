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


def normalized_weather():
    return {
        "provider": "open-meteo",
        "hourly": [
            {
                "time": f"2026-08-10T{index % 24:02d}:00",
                "temperature_2m": 29.0 + index * 0.1,
                "relative_humidity_2m": 45.0,
                "cloud_cover": 25.0,
                "shortwave_radiation": 550.0 if 7 <= index % 24 <= 19 else 0.0,
            }
            for index in range(49)
        ],
    }


def test_predictor_outputs_long_horizons() -> None:
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather=sample_weather(),
    )

    assert payload["horizons_minutes"][-1] == 2880
    assert len(payload["trajectories"]) == 3
    assert all(len(item["points"]) == 8 for item in payload["trajectories"])
    assert payload["weather_input"]["mode"] == "HOURLY_FORECAST"
    assert payload["weather_input"]["source_shape"] == "column_arrays"


def test_normalized_weather_service_rows_are_used_for_anticipation() -> None:
    weather = normalized_weather()
    weather["_source_route"] = "/geocooling/weather"
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather=weather,
    )

    quality = payload["weather_input"]
    assert quality["mode"] == "HOURLY_FORECAST"
    assert quality["degraded"] is False
    assert quality["provider"] == "open-meteo"
    assert quality["source_route"] == "/geocooling/weather"
    assert quality["source_shape"] == "normalized_rows"
    assert quality["forecast_points"] == 49
    assert quality["forecast_horizon_hours"] == 48

    baseline = next(
        item for item in payload["trajectories"] if item["scenario"] == "BASELINE"
    )
    assert baseline["points"][0]["outdoor_temperature_c"] != baseline["points"][-1]["outdoor_temperature_c"]


def test_current_weather_only_is_explicitly_degraded() -> None:
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather={"provider": "open-meteo", "current": {"temperature_2m": 31.5}},
    )

    assert payload["weather_input"]["mode"] == "CURRENT_FALLBACK"
    assert payload["weather_input"]["degraded"] is True
    assert payload["weather_input"]["forecast_horizon_hours"] == 0


def test_cooling_trajectory_is_below_baseline() -> None:
    payload = WeatherInertiaPredictor(
        ThermalModelParameters(model_confidence=0.8)
    ).predict(
        context=sample_context(),
        weather=sample_weather(),
    )

    trajectories = {
        item["scenario"]: item["points"]
        for item in payload["trajectories"]
    }

    assert (
        trajectories["FULL_COOLING"][-1]["predicted_indoor_temperature_c"]
        < trajectories["BASELINE"][-1]["predicted_indoor_temperature_c"]
    )


def test_predictor_never_authorizes_controller() -> None:
    payload = WeatherInertiaPredictor().predict(
        context=sample_context(),
        weather=normalized_weather(),
    )

    assert payload["safety"]["controller_authorized"] is False
    assert payload["safety"]["hardware_write"] is False
    assert payload["safety"]["mqtt_publish"] is False
    assert payload["safety"]["database_write"] is False
