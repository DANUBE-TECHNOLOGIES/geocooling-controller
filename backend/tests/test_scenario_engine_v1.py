from app.geocooling.scenario_engine_v1 import (
    ScenarioEngine,
)


def context(
    *,
    indoor=25.5,
    target=24.0,
    forecast_2h=26.0,
    margin=4.0,
    minimum_margin=3.0,
    confidence=0.8,
    blocking=False,
):
    return {
        "blocking": blocking,
        "measurements": {
            "indoor_temperature_c": indoor,
        },
        "configuration": {
            "comfort_target_c": target,
            "condensation_margin_c": margin,
            "minimum_condensation_margin_c": minimum_margin,
        },
        "recommendation": {
            "confidence": confidence,
        },
        "forecasts": [
            {
                "horizon_minutes": 120,
                "indoor_temperature_c": forecast_2h,
                "confidence": confidence,
                "source": "test",
            }
        ],
    }


def test_engine_returns_all_scenarios() -> None:
    decision = ScenarioEngine().evaluate(context())
    payload = decision.as_dict()

    names = {
        payload["selected"]["scenario"],
        *[
            item["scenario"]
            for item in payload["alternatives"]
        ],
    }

    assert names == {
        "WAIT",
        "PRECOOL_30",
        "PRECOOL_60",
        "COOL_NOW",
        "SOFT_COOLING",
    }


def test_engine_is_passive() -> None:
    payload = ScenarioEngine().evaluate(context()).as_dict()

    assert payload["passive"] is True
    assert payload["safety"] == {
        "hardware_write": False,
        "mqtt_publish": False,
        "database_write": False,
        "outbound_http": False,
    }


def test_blocking_context_penalizes_active_scenarios() -> None:
    payload = ScenarioEngine().evaluate(
        context(blocking=True)
    ).as_dict()

    assert payload["selected"]["scenario"] == "WAIT"


def test_low_margin_prefers_lower_intensity_or_wait() -> None:
    payload = ScenarioEngine().evaluate(
        context(
            margin=3.1,
            minimum_margin=3.0,
        )
    ).as_dict()

    assert payload["selected"]["scenario"] in {
        "WAIT",
        "SOFT_COOLING",
    }
