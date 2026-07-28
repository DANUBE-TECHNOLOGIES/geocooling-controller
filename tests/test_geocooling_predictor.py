from app.geocooling.predictor import GeoCoolingPredictor


def thermal_payload(*, indoor: float = 25.0, trend_30m: float | None = 0.6, running: bool = False) -> dict:
    return {
        "available": True,
        "latest": {
            "indoor_temperature_c": indoor,
            "outdoor_temperature_c": 32.0,
            "pump_running": running,
        },
        "cooling_power_kw": 4.0 if running else None,
        "trends_c_per_hour": {
            "indoor_5m": None,
            "indoor_30m": trend_30m,
            "indoor_120m": None,
        },
    }


def test_predictor_projects_measured_warming() -> None:
    predictor = GeoCoolingPredictor()
    result = predictor.predict(state="OFF", thermal=thermal_payload())
    assert result.available is True
    assert len(result.predictions) == 3
    assert result.predictions[-1].temperature_c > result.current_temperature_c
    assert result.confidence > 0


def test_predictor_projects_cooling_when_running() -> None:
    predictor = GeoCoolingPredictor()
    payload = thermal_payload(indoor=26.0, trend_30m=-0.5, running=True)
    result = predictor.predict(state="RUNNING", thermal=payload)
    assert result.available is True
    assert result.effective_trend_c_per_hour < 0
    assert result.predictions[-1].temperature_c < 26.0


def test_predictor_uses_physical_fallback_without_history() -> None:
    predictor = GeoCoolingPredictor()
    result = predictor.predict(
        state="OFF",
        thermal=thermal_payload(indoor=24.0, trend_30m=None),
    )
    assert result.available is True
    assert result.method == "physical_fallback"
    assert result.confidence == 35


def test_predictor_reports_unavailable_without_indoor_temperature() -> None:
    predictor = GeoCoolingPredictor()
    result = predictor.predict(
        state="OFF",
        thermal={"available": False, "latest": {}},
    )
    assert result.available is False
    assert result.predictions == ()


def test_predictor_default_horizons_focus_on_short_term_control() -> None:
    predictor = GeoCoolingPredictor()
    assert predictor.horizons_minutes == (30, 60, 120)

    result = predictor.predict(state="OFF", thermal=thermal_payload())
    assert [item.horizon_minutes for item in result.predictions] == [30, 60, 120]
