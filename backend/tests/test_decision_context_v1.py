from app.geocooling.decision_context_v1 import (
    DataQuality,
    DecisionAction,
    DecisionForecast,
    DecisionRisk,
    RiskLevel,
    build_decision_context,
    clamp_confidence,
)


def test_confidence_is_clamped() -> None:
    assert clamp_confidence(-1) == 0.0
    assert clamp_confidence(0.42) == 0.42
    assert clamp_confidence(2) == 1.0
    assert clamp_confidence("invalid") == 0.0


def test_context_serialization_contract() -> None:
    context = build_decision_context(
        timestamp="2026-08-03T10:00:00+00:00",
        measurements={
            "indoor_temperature_c": 25.4,
            "indoor_humidity_pct": 54,
            "dew_point_c": 15.4,
        },
        configuration={
            "comfort_target_c": 24.0,
            "condensation_margin_c": 4.1,
            "minimum_condensation_margin_c": 3.0,
            "building_inertia": "HIGH",
        },
        availability={
            "weather": True,
            "historian": True,
            "learning": False,
            "prediction": True,
            "hardware": False,
        },
        quality={
            "sensors": DataQuality.GOOD,
            "weather": DataQuality.GOOD,
            "learning": DataQuality.INSUFFICIENT,
            "prediction": DataQuality.DEGRADED,
        },
        forecasts=[
            DecisionForecast(
                horizon_minutes=120,
                indoor_temperature_c=25.9,
                confidence=0.72,
                source="thermal_prediction",
            )
        ],
        risks=[
            DecisionRisk(
                code="HARDWARE_UNAVAILABLE",
                level=RiskLevel.MEDIUM,
                message="Hardware not connected",
                blocking=False,
            )
        ],
        reasons=["Indoor temperature above target"],
        recommendation={
            "action": DecisionAction.WAIT,
            "confidence": 0.74,
        },
    )

    payload = context.as_dict()

    assert payload["schema"] == "geocooling.decision-context.v1"
    assert payload["recommendation"]["action"] == "WAIT"
    assert payload["recommendation"]["confidence"] == 0.74
    assert payload["availability"]["hardware"] is False
    assert payload["highest_risk_level"] == "MEDIUM"
    assert payload["blocking"] is False


def test_blocking_risk_is_reported() -> None:
    context = build_decision_context(
        risks=[
            DecisionRisk(
                code="CONDENSATION_CRITICAL",
                level=RiskLevel.CRITICAL,
                message="Condensation margin below minimum",
                blocking=True,
            )
        ],
        recommendation={
            "action": "BLOCKED",
            "confidence": 0.99,
        },
    )

    assert context.blocking is True
    assert context.highest_risk_level is RiskLevel.CRITICAL
    assert context.recommended_action is DecisionAction.BLOCKED


def test_invalid_values_do_not_break_context() -> None:
    context = build_decision_context(
        measurements={
            "indoor_temperature_c": "not-a-number",
            "flow_l_min": float("nan"),
        },
        quality={
            "sensors": "unknown-value",
        },
        recommendation={
            "action": "unknown-action",
            "confidence": "bad",
        },
    )

    assert context.indoor_temperature_c is None
    assert context.flow_l_min is None
    assert context.sensor_quality is DataQuality.UNKNOWN
    assert context.recommended_action is DecisionAction.WAIT
    assert context.confidence == 0.0
