from app.geocooling.decision_context_live_v1 import (
    LiveDecisionContextService,
    normalize_live_thermal_payload,
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


def test_live_thermal_aliases_are_normalized(monkeypatch) -> None:
    monkeypatch.setenv("GEOCOOLING_SURFACE_REFERENCE_MODE", "floor_loop_estimate")
    monkeypatch.setenv("GEOCOOLING_SURFACE_ESTIMATION_BIAS_C", "-0.5")

    payload = normalize_live_thermal_payload(
        {
            "indoor_temperature_c": 28.95,
            "indoor_humidity_percent": 42.4,
            "floor_supply_temperature_c": 26.5,
            "floor_return_temperature_c": 23.625,
            "source_inlet_temperature_c": 24.875,
            "source_outlet_temperature_c": 24.75,
            "flow_rate_l_min": None,
        }
    )

    assert payload is not None
    assert payload["indoor_humidity_pct"] == 42.4
    assert payload["source_in_temperature_c"] == 24.875
    assert payload["source_out_temperature_c"] == 24.75
    assert payload["floor_surface_temperature_c"] == 24.5625
    assert payload["surface_temperature_source"] == "floor_loop_estimate"


def test_live_context_accepts_production_thermal_names(monkeypatch) -> None:
    monkeypatch.setenv("GEOCOOLING_SURFACE_REFERENCE_MODE", "floor_loop_estimate")
    monkeypatch.setenv("GEOCOOLING_SURFACE_ESTIMATION_BIAS_C", "-0.5")

    client = FakeClient(
        {
            "/thermal": {
                "indoor_temperature_c": 28.95,
                "indoor_humidity_percent": 42.4,
                "dew_point_c": 15.0,
                "floor_supply_temperature_c": 26.5,
                "floor_return_temperature_c": 23.625,
                "source_inlet_temperature_c": 24.875,
                "source_outlet_temperature_c": 24.75,
            },
            "/weather": {"outdoor_temperature_c": 31.8},
            "/prediction": {"predicted_temperature_2h": 29.2},
            "/historian": {"available": True},
            "/hardware": {"ready": False},
            "/runtime": {"connected": True},
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

    payload = service.build_live_context()
    measurements = payload["measurements"]

    assert measurements["indoor_humidity_pct"] == 42.4
    assert measurements["source_in_temperature_c"] == 24.875
    assert measurements["source_out_temperature_c"] == 24.75
    assert measurements["floor_surface_temperature_c"] == 24.5625
    assert not any(
        risk["code"] == "INDOOR_HUMIDITY_MISSING"
        for risk in payload["risks"]
    )


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
