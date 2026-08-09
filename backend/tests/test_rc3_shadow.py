from app.geocooling.rc3.shadow import (
    ShadowDecisionService,
)


def test_shadow_never_authorizes_controller() -> None:
    service = ShadowDecisionService()

    result = service.compare(
        context_payload={
            "schema": "geocooling.decision-context.v1",
            "recommendation": {
                "action": "START_COOLING",
            },
            "measurements": {
                "indoor_temperature_c": 25.5,
            },
            "configuration": {},
            "risks": [],
        },
        scenario_payload={
            "schema": "geocooling.rc21.scenario-decision.v1",
            "selected": {
                "scenario": "COOL_NOW",
                "score": 0.9,
                "comfort_score": 0.9,
                "safety_score": 0.9,
                "energy_score": 0.7,
                "stability_score": 0.8,
                "learning_score": 0.6,
                "estimated_runtime_minutes": 90,
                "estimated_energy_kwh": 2.1,
                "reasons": [],
            },
            "alternatives": [],
        },
    )

    assert (
        result.rc3_output.controller_authorized
        is False
    )
    assert (
        result.rc3_output.selected_scenario
        == "COOL_NOW"
    )
