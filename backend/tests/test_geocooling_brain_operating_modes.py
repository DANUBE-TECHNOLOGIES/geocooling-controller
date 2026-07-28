from app.geocooling.brain import GeoCoolingBrain


def evaluate(
    *,
    indoor=None,
    humidity=None,
    outdoor=None,
    optional=None,
):
    optional = optional or {}

    latest = {
        "indoor_temperature_c": indoor,
        "indoor_humidity_percent": humidity,
        "outdoor_temperature_c": outdoor,
        "surface_temperature_c": optional.get("surface"),
        "floor_supply_temperature_c": optional.get("floor_supply"),
        "floor_return_temperature_c": optional.get("floor_return"),
        "source_inlet_temperature_c": optional.get("source_inlet"),
        "source_outlet_temperature_c": optional.get("source_outlet"),
        "flow_rate_l_min": optional.get("flow"),
        "pump_running": False,
    }

    brain = GeoCoolingBrain()

    return brain._c0123r4_original_evaluate(
        state="OFF",
        thermal={
            "available": True,
            "latest": latest,
            "cooling_power_kw": None,
            "floor_delta_t_c": None,
            "trends_c_per_hour": {},
        },
        safety={
            "safe": True,
            "margin_c": 5.0,
        },
        device={
            "ready": True,
        },
        anti_short_cycle={},
        prediction={},
    )


def test_building_only_with_three_building_measurements():
    result = evaluate(
        indoor=25.1,
        humidity=46.3,
        outdoor=26.8,
    )

    assert result.operating_mode == "BUILDING_ONLY"
    assert result.data_quality == 70
    assert result.confidence >= 0
    assert any(
        "Mode bâtiment uniquement" in reason
        for reason in result.reason
    )


def test_full_with_sufficient_optional_measurements():
    result = evaluate(
        indoor=25.1,
        humidity=46.3,
        outdoor=26.8,
        optional={
            "surface": 22.4,
            "floor_supply": 18.0,
            "floor_return": 20.5,
            "source_inlet": 12.3,
        },
    )

    assert result.operating_mode == "FULL"
    assert result.data_quality >= 90


def test_limited_with_two_building_measurements():
    result = evaluate(
        indoor=25.1,
        humidity=46.3,
        outdoor=None,
    )

    assert result.operating_mode == "LIMITED"
    assert result.data_quality == 47


def test_insufficient_data_with_one_building_measurement():
    result = evaluate(
        indoor=25.1,
        humidity=None,
        outdoor=None,
    )

    assert result.operating_mode == "INSUFFICIENT_DATA"
    assert result.data_quality == 23


def test_building_only_can_start_at_configured_temperature_threshold():
    result = evaluate(
        indoor=25.1,
        humidity=46.3,
        outdoor=26.8,
    )

    assert result.operating_mode == "BUILDING_ONLY"
    assert result.decision == "START"
    assert result.total_score == result.comfort_score


def test_insufficient_data_never_starts_when_system_is_off():
    result = evaluate(
        indoor=28.0,
        humidity=None,
        outdoor=None,
    )

    assert result.operating_mode == "INSUFFICIENT_DATA"
    assert result.decision == "WAIT"
    assert result.recommended_runtime_minutes == 0
    assert any(
        "Démarrage interdit" in reason
        for reason in result.reason
    )


def test_brain_keeps_mode_during_single_transient_sensor_loss():
    brain = GeoCoolingBrain()

    def run(indoor, humidity, outdoor, optional=None):
        optional = optional or {}
        latest = {
            "indoor_temperature_c": indoor,
            "indoor_humidity_percent": humidity,
            "outdoor_temperature_c": outdoor,
            "surface_temperature_c": optional.get("surface"),
            "floor_supply_temperature_c": optional.get("floor_supply"),
            "floor_return_temperature_c": optional.get("floor_return"),
            "source_inlet_temperature_c": optional.get("source_inlet"),
            "source_outlet_temperature_c": optional.get("source_outlet"),
            "flow_rate_l_min": optional.get("flow"),
            "pump_running": False,
        }
        return brain._c0123r4_original_evaluate(
            state="OFF",
            thermal={
                "available": True,
                "latest": latest,
                "cooling_power_kw": None,
                "floor_delta_t_c": None,
                "trends_c_per_hour": {},
            },
            safety={"safe": True, "margin_c": 5.0},
            device={"ready": True},
            anti_short_cycle={},
            prediction={},
        )

    full = run(
        25.1,
        46.3,
        26.8,
        {
            "surface": 22.4,
            "floor_supply": 18.0,
            "floor_return": 20.5,
            "source_inlet": 12.3,
        },
    )
    transient = run(25.1, 46.3, None)

    assert full.operating_mode == "FULL"
    assert transient.operating_mode == "FULL"
    assert any(
        "LIMITED en attente de confirmation" in reason
        for reason in transient.reason
    )


def test_brain_confirms_degradation_after_two_cycles():
    brain = GeoCoolingBrain()

    def run(outdoor):
        latest = {
            "indoor_temperature_c": 25.1,
            "indoor_humidity_percent": 46.3,
            "outdoor_temperature_c": outdoor,
            "surface_temperature_c": 22.4,
            "floor_supply_temperature_c": 18.0,
            "floor_return_temperature_c": 20.5,
            "source_inlet_temperature_c": 12.3,
            "source_outlet_temperature_c": None,
            "flow_rate_l_min": None,
            "pump_running": False,
        }
        return brain._c0123r4_original_evaluate(
            state="OFF",
            thermal={
                "available": True,
                "latest": latest,
                "cooling_power_kw": None,
                "floor_delta_t_c": None,
                "trends_c_per_hour": {},
            },
            safety={"safe": True, "margin_c": 5.0},
            device={"ready": True},
            anti_short_cycle={},
            prediction={},
        )

    run(26.8)
    first_loss = run(None)
    confirmed_loss = run(None)

    assert first_loss.operating_mode == "FULL"
    assert confirmed_loss.operating_mode == "LIMITED"
    assert any("FULL → LIMITED" in reason for reason in confirmed_loss.reason)
