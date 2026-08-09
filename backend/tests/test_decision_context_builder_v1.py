from app.geocooling.decision_context_builder_v1 import (
    PassiveDecisionContextBuilder,
)


def test_builder_produces_passive_context() -> None:
    context = PassiveDecisionContextBuilder().build(
        thermal={
            "indoor_temperature": 25.6,
            "indoor_humidity": 54.0,
            "dew_point": 15.5,
            "condensation_margin": 4.0,
        },
        weather={
            "outdoor_temperature": 30.0,
        },
        prediction={
            "predicted_temperature_2h": 26.1,
            "confidence": 0.8,
        },
        historian={"available": True},
        configuration={
            "comfort_target_c": 24.0,
            "cooling_start_threshold_c": 25.0,
            "cooling_stop_threshold_c": 23.8,
            "minimum_condensation_margin_c": 3.0,
        },
    )

    payload = context.as_dict()

    assert payload["schema"] == "geocooling.decision-context.v1"
    assert payload["metadata"]["mode"] == "passive"
    assert payload["availability"]["hardware"] is False
    assert payload["recommendation"]["action"] == "WAIT"
    assert payload["forecasts"][0]["horizon_minutes"] == 120


def test_builder_blocks_missing_core_sensors() -> None:
    context = PassiveDecisionContextBuilder().build()

    assert context.blocking is True
    assert context.recommended_action.value == "BLOCKED"


def test_builder_blocks_low_condensation_margin() -> None:
    context = PassiveDecisionContextBuilder().build(
        thermal={
            "indoor_temperature": 26.0,
            "indoor_humidity": 60.0,
            "condensation_margin": 1.5,
        },
        hardware={"ready": True},
        configuration={
            "cooling_start_threshold_c": 25.0,
            "minimum_condensation_margin_c": 3.0,
        },
    )

    assert context.blocking is True
    assert context.recommended_action.value == "BLOCKED"
