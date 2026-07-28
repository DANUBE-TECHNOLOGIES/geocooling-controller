from app.geocooling.mission_supervisor import GeoCoolingMissionSupervisor


class Brain:
    def __init__(self, decision="COOL"):
        self.decision = decision
    def decide(self, payload):
        return {"decision": self.decision, "timing": {"recommended_runtime_minutes": 120}, "targets": {"predicted_final_temperature_c": 24.5}, "physical_activation_allowed": False}


def test_start_is_simulation_only(tmp_path):
    m = GeoCoolingMissionSupervisor(Brain(), str(tmp_path / "m.json"))
    result = m.start({"indoor_temperature_c": 27.0})
    assert result["state"] == "RUNNING_SIMULATION"
    assert result["hardware_touched"] is False


def test_blocked_brain_refuses_mission(tmp_path):
    m = GeoCoolingMissionSupervisor(Brain("BLOCKED"), str(tmp_path / "m.json"))
    try:
        m.start({})
        assert False
    except ValueError:
        assert True


def test_deviation_triggers_interlock(tmp_path):
    m = GeoCoolingMissionSupervisor(Brain(), str(tmp_path / "m.json"))
    m.start({"indoor_temperature_c": 27.0})
    result = m.update({"elapsed_minutes": 30, "observed_temperature_c": 27.0, "maximum_deviation_c": 1.0})
    assert result["state"] == "STOPPED_INTERLOCK"
    assert result["software_interlock"] is True


def test_runtime_completion_archives(tmp_path):
    m = GeoCoolingMissionSupervisor(Brain(), str(tmp_path / "m.json"))
    m.start({"indoor_temperature_c": 27.0})
    result = m.update({"elapsed_minutes": 120, "observed_temperature_c": 24.5})
    assert result["state"] == "COMPLETED"
    assert m.status()["active_mission"] is None


def test_operator_stop_and_persistence(tmp_path):
    path = str(tmp_path / "m.json")
    m = GeoCoolingMissionSupervisor(Brain(), path)
    m.start({"indoor_temperature_c": 27.0})
    m.stop("TEST")
    loaded = GeoCoolingMissionSupervisor(Brain(), path)
    assert loaded.missions(1)[0]["stop_reason"] == "TEST"
