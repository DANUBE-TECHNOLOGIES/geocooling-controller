from app.geocooling.rc3.live_shadow import (
    LiveShadowRunner,
)


class FakeClient:
    def get_json(self, route):
        if route == "/geocooling/decision-context/live":
            return {
                "schema": "geocooling.decision-context.v1",
                "timestamp": "2026-08-03T12:00:00+00:00",
                "measurements": {
                    "indoor_temperature_c": 25.4,
                },
                "configuration": {},
                "recommendation": {
                    "action": "WAIT",
                },
                "risks": [],
            }

        if route == "/geocooling/scenario-engine/live":
            return {
                "scenario_decision": {
                    "schema": "geocooling.rc21.scenario-decision.v1",
                    "selected": {
                        "scenario": "WAIT",
                        "score": 0.8,
                        "comfort_score": 0.8,
                        "safety_score": 1.0,
                        "energy_score": 1.0,
                        "stability_score": 0.9,
                        "learning_score": 0.5,
                        "estimated_runtime_minutes": 0,
                        "estimated_energy_kwh": 0.0,
                        "reasons": [],
                    },
                    "alternatives": [],
                }
            }

        raise RuntimeError(route)


def test_live_shadow_runner_is_passive() -> None:
    payload = LiveShadowRunner(
        client=FakeClient(),
    ).run()

    assert payload["mode"] == "SHADOW"
    assert payload["activation"] == {
        "controller_authorized": False,
        "controller_called": False,
        "hardware_called": False,
        "selected_scenario_activated": False,
    }
    assert payload["safety"]["outbound_http_methods"] == ["GET"]
