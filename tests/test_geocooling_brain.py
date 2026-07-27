from app.geocooling.brain import GeoCoolingBrain


def thermal_payload(*, indoor: float, power: float = 4.0, running: bool = False) -> dict:
    return {
        "available": True,
        "latest": {
            "indoor_temperature_c": indoor,
            "indoor_humidity_percent": 55.0,
            "surface_temperature_c": 20.0,
            "outdoor_temperature_c": 32.0,
            "source_inlet_temperature_c": 12.0,
            "flow_rate_l_min": 20.0,
            "pump_running": running,
        },
        "floor_delta_t_c": 2.5,
        "cooling_power_kw": power,
        "trends_c_per_hour": {"indoor_30m": -0.4},
    }


def test_brain_recommends_start_when_house_is_hot() -> None:
    brain = GeoCoolingBrain()
    decision = brain.evaluate(
        state="OFF",
        thermal=thermal_payload(indoor=27.0),
        safety={"safe": True, "margin_c": 5.0},
        device={"ready": True},
        anti_short_cycle={"remaining_minimum_off_seconds": 0},
    )
    assert decision.decision == "START"
    assert decision.confidence >= 50


def test_brain_blocks_on_condensation_risk() -> None:
    brain = GeoCoolingBrain()
    decision = brain.evaluate(
        state="OFF",
        thermal=thermal_payload(indoor=28.0),
        safety={"safe": False, "margin_c": 0.5, "reason": "Condensation"},
        device={"ready": True},
    )
    assert decision.decision == "BLOCKED"
    assert decision.risk_score == 100


def test_brain_stops_when_target_is_reached() -> None:
    brain = GeoCoolingBrain()
    decision = brain.evaluate(
        state="RUNNING",
        thermal=thermal_payload(indoor=23.0, running=True),
        safety={"safe": True, "margin_c": 5.0},
        device={"ready": True},
        anti_short_cycle={"remaining_minimum_on_seconds": 0},
    )
    assert decision.decision == "STOP"


def test_brain_waits_during_minimum_off_time() -> None:
    brain = GeoCoolingBrain()
    decision = brain.evaluate(
        state="OFF",
        thermal=thermal_payload(indoor=28.0),
        safety={"safe": True, "margin_c": 5.0},
        device={"ready": True},
        anti_short_cycle={"remaining_minimum_off_seconds": 120},
    )
    assert decision.decision == "WAIT"
