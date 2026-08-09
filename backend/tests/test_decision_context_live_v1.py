from app.geocooling.decision_context_live_v1 import (
    LiveDecisionContextService,
)


class FakeClient:
    def __init__(self, payloads):
        self.payloads = payloads
        self.calls = []

    def get_json(self, route):
        self.calls.append(route)

        if route not in self.payloads:
            raise RuntimeError("missing")

        return self.payloads[route]


def test_live_service_uses_get_only_client() -> None:
    client = FakeClient(
        {
            "/thermal": {
                "indoor_temperature": 25.4,
                "indoor_humidity": 54,
                "condensation_margin": 4.2,
            },
            "/weather": {
                "outdoor_temperature": 30.0,
            },
            "/prediction": {
                "predicted_temperature_2h": 25.9,
            },
            "/historian": {
                "available": True,
            },
            "/hardware": {
                "ready": False,
            },
            "/runtime": {
                "connected": True,
            },
        }
    )

    service = LiveDecisionContextService(
        client=client,
        routes={
            "thermal": ("/thermal",),
            "weather": ("/weather",),
            "prediction": ("/prediction",),
            "learning": ("/learning",),
            "historian": ("/historian",),
            "hardware": ("/hardware",),
            "runtime": ("/runtime",),
        },
    )

    payload = service.build_live_context(
        configuration={
            "comfort_target_c": 24,
            "cooling_start_threshold_c": 25,
            "cooling_stop_threshold_c": 23.8,
            "minimum_condensation_margin_c": 3,
        }
    )

    assert payload["live_mode"]["http_methods_used"] == ["GET"]
    assert payload["live_mode"]["hardware_write"] is False
    assert payload["recommendation"]["action"] == "WAIT"
    assert payload["availability"]["weather"] is True


def test_source_failure_is_non_fatal() -> None:
    service = LiveDecisionContextService(
        client=FakeClient({}),
        routes={
            "thermal": ("/thermal",),
            "weather": ("/weather",),
            "prediction": ("/prediction",),
            "learning": ("/learning",),
            "historian": ("/historian",),
            "hardware": ("/hardware",),
            "runtime": ("/runtime",),
        },
    )

    payload = service.build_live_context()

    assert payload["recommendation"]["action"] == "BLOCKED"
    assert payload["live_sources"]["thermal"]["available"] is False
