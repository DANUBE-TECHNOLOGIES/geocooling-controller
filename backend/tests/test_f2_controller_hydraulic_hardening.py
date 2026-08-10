import sys
import threading
import types

# Keep controller imports independent from an installed MQTT client.
paho = types.ModuleType("paho")
paho_mqtt = types.ModuleType("paho.mqtt")
paho_client = types.ModuleType("paho.mqtt.client")
paho_client.Client = object
paho_client.MQTTMessage = object
paho_client.CallbackAPIVersion = types.SimpleNamespace(VERSION2=2)
sys.modules.setdefault("paho", paho)
sys.modules.setdefault("paho.mqtt", paho_mqtt)
sys.modules.setdefault("paho.mqtt.client", paho_client)

from app.geocooling.controller import GeoCoolingController
from app.geocooling.models import GeoCoolingState


class TrackingDriver:
    def __init__(self, *, fail_safe_state=False):
        self.valve_open = False
        self.pump_running = False
        self.start_pump_calls = 0
        self.fail_safe_state = fail_safe_state

    def open_valve(self):
        self.valve_open = True

    def start_pump(self):
        self.start_pump_calls += 1
        self.pump_running = True

    def stop_pump(self):
        self.pump_running = False

    def close_valve(self):
        self.valve_open = False

    def force_safe_state(self):
        if self.fail_safe_state:
            raise RuntimeError("rollback unavailable")
        self.pump_running = False
        self.valve_open = False

    def status(self):
        return {
            "valve_open": self.valve_open,
            "pump_running": self.pump_running,
        }


def bare_controller(state=GeoCoolingState.OFF):
    controller = GeoCoolingController.__new__(GeoCoolingController)
    controller._lock = threading.RLock()
    controller.state = state
    controller.state_changed_at = None
    controller.last_event = "test"
    controller.last_reason = "test"
    controller.last_error = None
    controller.stopped_at = None
    controller.driver_name = "simulation"
    controller.driver = TrackingDriver()
    controller.status = lambda: {"state": controller.state.value}
    return controller


def test_start_is_rejected_from_fault_until_explicit_reset():
    controller = bare_controller(GeoCoolingState.FAULT)

    result = controller.request_start()

    assert result["accepted"] is False
    assert "reset explicite" in result["message"]
    assert controller.state == GeoCoolingState.FAULT


def test_start_is_rejected_from_emergency_stop_until_explicit_reset():
    controller = bare_controller(GeoCoolingState.EMERGENCY_STOP)

    result = controller.request_start()

    assert result["accepted"] is False
    assert "reset explicite" in result["message"]
    assert controller.state == GeoCoolingState.EMERGENCY_STOP


def test_real_hardware_start_is_rejected_before_any_actuation_when_commissioning_not_ready():
    controller = bare_controller(GeoCoolingState.OFF)
    controller.driver_name = "waveshare_modbus"
    controller._commissioning_readiness = lambda: {
        "state": "IDENTIFICATION_REQUIRED",
        "ready_for_release": False,
        "next_action": "Confirm physical sensor identity before assigning mappings.",
        "read_only": True,
        "hardware_touched": False,
    }

    result = controller.request_start()

    assert result["accepted"] is False
    assert "Commissioning Gate" in result["message"]
    assert result["commissioning_readiness"]["state"] == "IDENTIFICATION_REQUIRED"
    assert controller.driver.valve_open is False
    assert controller.driver.pump_running is False
    assert controller.driver.start_pump_calls == 0
    assert controller.state == GeoCoolingState.OFF


def test_simulation_commissioning_readiness_is_non_blocking_and_read_only():
    controller = bare_controller(GeoCoolingState.OFF)

    readiness = controller._commissioning_readiness()

    assert readiness["state"] == "SIMULATION"
    assert readiness["ready_for_release"] is True
    assert readiness["read_only"] is True
    assert readiness["hardware_touched"] is False


def test_thermal_safety_is_rechecked_before_m11_m13_start():
    controller = bare_controller()
    controller.valve_open_delay = 0.0
    controller.cycle_count = 0
    controller.started_at = None

    transitions = []
    safe_stop_reasons = []

    def transition(new_state, event_type, reason):
        controller.state = new_state
        transitions.append((new_state, event_type, reason))

    controller._transition = transition
    controller._wait_for_actuator_state = lambda **kwargs: {}
    controller._interruptible_wait = lambda seconds: False
    controller._thermal_safety = lambda: {
        "safe": False,
        "reason": "marge de condensation insuffisante",
    }
    controller._safe_stop_sequence = safe_stop_reasons.append

    controller._start_sequence()

    assert controller.driver.valve_open is True
    assert controller.driver.start_pump_calls == 0
    assert safe_stop_reasons == [
        "Démarrage interrompu avant M11+M13 : "
        "marge de condensation insuffisante"
    ]
    assert all(
        state != GeoCoolingState.STARTING_PUMP
        for state, _, _ in transitions
    )


def test_fault_state_is_deterministic_even_when_rollback_and_persistence_fail():
    controller = bare_controller(GeoCoolingState.RUNNING)
    controller.driver = TrackingDriver(fail_safe_state=True)

    def failed_transition(*args, **kwargs):
        raise RuntimeError("persistence unavailable")

    controller._transition = failed_transition

    controller._enter_fault("feedback write failed")

    assert controller.state == GeoCoolingState.FAULT
    assert controller.last_event == "geocooling.fault"
    assert "feedback write failed" in controller.last_error
    assert "rollback unavailable" in controller.last_error
