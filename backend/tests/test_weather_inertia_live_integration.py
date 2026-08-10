from app.geocooling.rc3.weather_inertia_live import LiveWeatherInertiaPredictionService


class FakeClient:
    def __init__(self):
        self.calls = []

    def get_json(self, route):
        self.calls.append(route)
        if route == "/geocooling/decision-context/live":
            return {
                "measurements": {
                    "indoor_temperature_c": 25.2,
                    "outdoor_temperature_c": 30.0,
                    "floor_surface_temperature_c": 23.8,
                }
            }
        if route == "/geocooling/weather":
            return {
                "provider": "open-meteo",
                "hourly": [
                    {
                        "time": f"2026-08-{10 + (index // 24):02d}T{index % 24:02d}:00",
                        "temperature_2m": 29.0 + index * 0.08,
                        "relative_humidity_2m": 45.0,
                        "cloud_cover": 30.0,
                        "shortwave_radiation": 500.0 if 7 <= index % 24 <= 19 else 0.0,
                    }
                    for index in range(49)
                ],
            }
        raise RuntimeError(f"unexpected route: {route}")


def test_live_service_prefers_geocooling_weather_and_uses_hourly_forecast():
    client = FakeClient()
    payload = LiveWeatherInertiaPredictionService(client=client).predict()

    assert client.calls[:2] == [
        "/geocooling/decision-context/live",
        "/geocooling/weather",
    ]
    assert payload["sources"]["weather"] == "/geocooling/weather"
    assert payload["weather_input"]["mode"] == "HOURLY_FORECAST"
    assert payload["weather_input"]["source_shape"] == "normalized_rows"
    assert payload["weather_input"]["forecast_horizon_hours"] == 48
    assert payload["weather_input"]["degraded"] is False
    assert payload["safety"]["controller_authorized"] is False
    assert payload["safety"]["hardware_write"] is False


def test_live_service_can_fall_back_but_marks_degraded_mode():
    class CurrentOnlyClient(FakeClient):
        def get_json(self, route):
            if route == "/geocooling/decision-context/live":
                return super().get_json(route)
            if route == "/geocooling/weather":
                return {"provider": "open-meteo", "current": {"temperature_2m": 31.0}}
            raise RuntimeError(route)

    payload = LiveWeatherInertiaPredictionService(client=CurrentOnlyClient()).predict()

    assert payload["weather_input"]["mode"] == "CURRENT_FALLBACK"
    assert payload["weather_input"]["degraded"] is True
    assert payload["safety"]["hardware_write"] is False
