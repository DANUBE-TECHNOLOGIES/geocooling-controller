from app.geocooling.brain_v5 import GeoCoolingBrainV5


class Optimizer:
    def __init__(self, action="COOL", condensation=False, runtime=120, efficiency=0.8):
        self.action = action
        self.condensation = condensation
        self.runtime = runtime
        self.efficiency = efficiency

    def optimize(self, payload):
        return {
            "recommended_action": self.action,
            "recommended_start_hour": 2 if self.action == "COOL" else None,
            "recommended_runtime_minutes": self.runtime if self.action == "COOL" else 0,
            "estimated_energy_kwh": 1.2 if self.action == "COOL" else 0.0,
            "thermal_gain_c": 1.1 if self.action == "COOL" else 0.0,
            "efficiency_index": self.efficiency,
            "estimated_starts": 1 if self.action == "COOL" else 0,
            "optimized": {"final_temperature_c": 24.7, "condensation_interlock": self.condensation},
        }


def brain(opt):
    return GeoCoolingBrainV5(opt, object(), object())


def test_cooling_decision_is_explainable_and_safe():
    result = brain(Optimizer()).decide({"target_temperature_c": 24.0})
    assert result["decision"] == "COOL"
    assert result["confidence"]["level"] == "HIGH"
    assert result["why"]
    assert result["automatic_execution_allowed"] is False
    assert result["physical_activation_allowed"] is False


def test_hold_decision_has_zero_runtime():
    result = brain(Optimizer(action="HOLD")).decide({"target_temperature_c": 24.0})
    assert result["decision"] == "HOLD"
    assert result["timing"]["recommended_runtime_minutes"] == 0


def test_condensation_blocks_decision():
    result = brain(Optimizer(condensation=True)).decide({"target_temperature_c": 24.0})
    assert result["decision"] == "BLOCKED"
    assert result["timing"]["recommended_runtime_minutes"] == 0
    assert result["risks"][0]["code"] == "CONDENSATION_INTERLOCK"


def test_long_runtime_reduces_confidence():
    result = brain(Optimizer(runtime=360)).decide({"target_temperature_c": 24.0})
    assert result["confidence"]["score"] < 0.9
    assert any(r["code"] == "LONG_RUNTIME" for r in result["risks"])


def test_status_keeps_last_decision():
    instance = brain(Optimizer())
    assert instance.status()["last_decision"] is None
    instance.decide({"target_temperature_c": 24.0})
    assert instance.status()["last_decision"]["decision"] == "COOL"
