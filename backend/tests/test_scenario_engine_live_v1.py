from app.geocooling.scenario_engine_live_v1 import (
    LiveScenarioEngineService,
)


class FakeContextService:
    def build_live_context(self, configuration=None):
        return {
            "blocking": False,
            "measurements": {
                "indoor_temperature_c": 25.5,
            },
            "configuration": {
                "comfort_target_c": 24.0,
                "condensation_margin_c": 4.5,
                "minimum_condensation_margin_c": 3.0,
            },
            "recommendation": {
                "confidence": 0.8,
            },
            "forecasts": [
                {
                    "horizon_minutes": 120,
                    "indoor_temperature_c": 26.0,
                    "confidence": 0.8,
                    "source": "test",
                }
            ],
            "live_sources": {},
        }

    def source_status(self):
        return {
            "sources": {
                "thermal": {
                    "available": True,
                },
                "weather": {
                    "available": True,
                },
            }
        }


def test_live_scenario_service_is_passive() -> None:
    service = LiveScenarioEngineService(
        context_service=FakeContextService(),
    )

    payload = service.evaluate_live()

    assert payload["mode"] == "passive"
    assert payload["activation"] == {
        "selected_scenario_activated": False,
        "controller_called": False,
        "hardware_called": False,
    }
    assert payload["safety"]["hardware_write"] is False
    assert payload["scenario_decision"]["selected"]["scenario"]


def test_health_reports_sources() -> None:
    service = LiveScenarioEngineService(
        context_service=FakeContextService(),
    )

    health = service.health()

    assert health["ready"] is True
    assert health["available_sources"] == 2
    assert health["hardware_write"] is False
