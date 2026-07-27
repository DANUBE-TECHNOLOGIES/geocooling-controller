from app.geocooling.decision_context import (
    GeoCoolingDecisionContext,
)


def number_parser(value):
    if value is None:
        return None

    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def build_context(
    *,
    state="OFF",
    latest=None,
    thermal=None,
    safety=None,
    device=None,
    anti_short_cycle=None,
    predictions=None,
):
    return GeoCoolingDecisionContext.build(
        state=state,
        latest=latest or {},
        thermal=thermal or {},
        safety=safety or {},
        device=device or {},
        anti_short_cycle=anti_short_cycle or {},
        prediction_by_horizon=predictions or {},
        number_parser=number_parser,
    )


def test_running_context():
    context = build_context(
        state="RUNNING",
        latest={
            "indoor_temperature_c": 25.1,
        },
        thermal={
            "available": True,
            "cooling_power_kw": 1.8,
        },
        safety={
            "safe": True,
        },
        device={
            "ready": True,
        },
    )

    assert context.running is True
    assert context.indoor_temperature_c == 25.1
    assert context.cooling_power_kw == 1.8
    assert context.blocked_by_infrastructure is False


def test_blocked_when_safety_is_not_safe():
    context = build_context(
        safety={
            "safe": False,
        },
        device={
            "ready": True,
        },
    )

    assert context.blocked_by_infrastructure is True


def test_blocked_when_device_is_not_ready():
    context = build_context(
        safety={
            "safe": True,
        },
        device={
            "ready": False,
        },
    )

    assert context.blocked_by_infrastructure is True


def test_anti_short_cycle_values():
    context = build_context(
        anti_short_cycle={
            "remaining_minimum_off_seconds": 120,
            "remaining_minimum_on_seconds": 45,
        },
    )

    assert context.minimum_off_active is True
    assert context.minimum_on_active is True
    assert context.remaining_minimum_off_seconds == 120
    assert context.remaining_minimum_on_seconds == 45


def test_negative_anti_short_cycle_is_clamped():
    context = build_context(
        anti_short_cycle={
            "remaining_minimum_off_seconds": -10,
            "remaining_minimum_on_seconds": -20,
        },
    )

    assert context.remaining_minimum_off_seconds == 0
    assert context.remaining_minimum_on_seconds == 0


def test_predictions_are_parsed():
    context = build_context(
        predictions={
            60: "24.9",
            180: "25.6",
            360: "26.4",
        },
    )

    assert context.predicted_temperature_1h_c == 24.9
    assert context.predicted_temperature_3h_c == 25.6
    assert context.predicted_temperature_6h_c == 26.4


def test_invalid_measurements_become_none():
    context = build_context(
        latest={
            "indoor_temperature_c": "invalid",
        },
        thermal={
            "cooling_power_kw": "invalid",
        },
    )

    assert context.indoor_temperature_c is None
    assert context.cooling_power_kw is None


def test_serialization():
    context = build_context(
        state="RUNNING",
        latest={
            "indoor_temperature_c": 25.1,
        },
        thermal={
            "available": True,
            "cooling_power_kw": 1.8,
        },
        safety={
            "safe": True,
        },
        device={
            "ready": True,
        },
    )

    payload = context.as_dict()

    assert payload["state"] == "RUNNING"
    assert payload["running"] is True
    assert payload["indoor_temperature_c"] == 25.1
    assert payload["blocked_by_infrastructure"] is False
