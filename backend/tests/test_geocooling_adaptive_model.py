from datetime import datetime, timedelta, timezone
from types import SimpleNamespace

from app.geocooling.adaptive_model import (
    AdaptiveThermalModel,
)
from app.geocooling.predictor import (
    GeoCoolingPredictor,
)


BASE_TIME = datetime(
    2026,
    7,
    27,
    10,
    0,
    tzinfo=timezone.utc,
)


def snapshot(
    *,
    minutes: int,
    indoor: float,
    outdoor: float,
    running: bool,
):
    return SimpleNamespace(
        timestamp=BASE_TIME + timedelta(
            minutes=minutes
        ),
        indoor_temperature_c=indoor,
        outdoor_temperature_c=outdoor,
        pump_running=running,
    )


def test_passive_learning():
    model = AdaptiveThermalModel()
    model.minimum_observation_seconds = 60

    previous = snapshot(
        minutes=0,
        indoor=24.0,
        outdoor=30.0,
        running=False,
    )
    current = snapshot(
        minutes=30,
        indoor=24.3,
        outdoor=30.0,
        running=False,
    )

    assert model.observe(
        previous=previous,
        current=current,
        cooling_power_kw=None,
    )

    estimate = model.estimate()

    assert estimate.passive_sample_count == 1
    assert (
        estimate.natural_temperature_rate_c_per_hour
        == 0.6
    )
    assert (
        estimate.passive_exchange_rate_per_hour
        is not None
    )


def test_active_learning():
    model = AdaptiveThermalModel()
    model.minimum_observation_seconds = 60

    passive_previous = snapshot(
        minutes=0,
        indoor=24.0,
        outdoor=30.0,
        running=False,
    )
    passive_current = snapshot(
        minutes=30,
        indoor=24.3,
        outdoor=30.0,
        running=False,
    )

    model.observe(
        previous=passive_previous,
        current=passive_current,
        cooling_power_kw=None,
    )

    active_previous = snapshot(
        minutes=60,
        indoor=25.0,
        outdoor=30.0,
        running=True,
    )
    active_current = snapshot(
        minutes=90,
        indoor=24.6,
        outdoor=30.0,
        running=True,
    )

    assert model.observe(
        previous=active_previous,
        current=active_current,
        cooling_power_kw=4.0,
    )

    estimate = model.estimate()

    assert estimate.active_sample_count == 1
    assert (
        estimate.active_cooling_rate_c_per_hour
        is not None
    )
    assert (
        estimate.house_thermal_capacity_kwh_per_c
        is not None
    )


def test_transition_sample_is_rejected():
    model = AdaptiveThermalModel()
    model.minimum_observation_seconds = 60

    previous = snapshot(
        minutes=0,
        indoor=25.0,
        outdoor=30.0,
        running=False,
    )
    current = snapshot(
        minutes=10,
        indoor=24.9,
        outdoor=30.0,
        running=True,
    )

    assert not model.observe(
        previous=previous,
        current=current,
        cooling_power_kw=4.0,
    )


def test_model_becomes_available():
    model = AdaptiveThermalModel()
    model.minimum_observation_seconds = 60

    points = [
        snapshot(
            minutes=0,
            indoor=24.0,
            outdoor=30.0,
            running=False,
        ),
        snapshot(
            minutes=10,
            indoor=24.1,
            outdoor=30.0,
            running=False,
        ),
        snapshot(
            minutes=20,
            indoor=24.2,
            outdoor=30.0,
            running=False,
        ),
        snapshot(
            minutes=30,
            indoor=24.3,
            outdoor=30.0,
            running=False,
        ),
    ]

    for previous, current in zip(
        points,
        points[1:],
    ):
        model.observe(
            previous=previous,
            current=current,
            cooling_power_kw=None,
        )

    estimate = model.estimate()

    assert estimate.available is True
    assert estimate.total_sample_count == 3
    assert estimate.confidence > 0


def test_predictor_uses_adaptive_active_rate():
    predictor = GeoCoolingPredictor()

    thermal = {
        "latest": {
            "indoor_temperature_c": 25.0,
            "outdoor_temperature_c": 25.0,
            "pump_running": True,
        },
        "cooling_power_kw": 4.0,
        "adaptive_model": {
            "available": True,
            "confidence": 80,
            "passive_exchange_rate_per_hour": 0.10,
            "active_cooling_rate_c_per_hour": 0.75,
            "house_thermal_capacity_kwh_per_c": 12.0,
        },
    }

    trend, reasons = predictor._model_trend(
        thermal,
        "RUNNING",
    )

    assert trend == -0.75
    assert any(
        "appris" in reason
        for reason in reasons
    )


def test_predictor_falls_back_to_defaults():
    predictor = GeoCoolingPredictor()

    thermal = {
        "latest": {
            "indoor_temperature_c": 25.0,
            "outdoor_temperature_c": 30.0,
            "pump_running": False,
        },
        "adaptive_model": {
            "available": False,
            "confidence": 0,
        },
    }

    trend, reasons = predictor._model_trend(
        thermal,
        "OFF",
    )

    expected = (
        30.0
        - 25.0
    ) * predictor.passive_exchange_rate_per_hour

    assert trend == expected
    assert reasons
