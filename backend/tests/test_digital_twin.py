from app.geocooling.digital_twin import GeoCoolingDigitalTwin

def test_initial(tmp_path):
    twin = GeoCoolingDigitalTwin(str(tmp_path / "twin.json"))
    assert twin.status()["status"] == "NOT_INITIALIZED"
    assert twin.status()["hardware_touched"] is False

def test_complete_state(tmp_path):
    twin = GeoCoolingDigitalTwin(str(tmp_path / "twin.json"))
    state = twin.update({
        "indoor_temperature_c": 26.1,
        "upstairs_temperature_c": 26.8,
        "outdoor_temperature_c": 31.5,
        "indoor_humidity_percent": 54.0,
        "floor_surface_temperature_c": 22.4,
        "supply_temperature_c": 18.0,
        "return_temperature_c": 20.5,
        "source_in_temperature_c": 12.3,
        "source_out_temperature_c": 15.0,
        "flow_l_min": 28.0,
        "pump_running": True,
        "valve_open": True,
    })
    assert state["status"] == "READY"
    assert state["active_cooling"] is True
    assert state["secondary_delta_t_c"] == 2.5
    assert state["source_delta_t_c"] == 2.7

def test_inconsistent_actuator_state(tmp_path):
    twin = GeoCoolingDigitalTwin(str(tmp_path / "twin.json"))
    state = twin.update({"indoor_temperature_c": 25, "pump_running": True, "valve_open": False})
    assert "PUMP_VALVE_STATE_INCONSISTENT" in state["observations"]

def test_condensation(tmp_path):
    twin = GeoCoolingDigitalTwin(str(tmp_path / "twin.json"))
    state = twin.update({"indoor_temperature_c": 26, "indoor_humidity_percent": 75, "floor_surface_temperature_c": 20})
    assert state["condensation_risk"] in {"HIGH", "CRITICAL"}
