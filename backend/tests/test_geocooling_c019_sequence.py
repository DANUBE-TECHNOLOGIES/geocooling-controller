import sys
import threading
import types

import pytest

# Le poste de fabrication du patch ne charge pas les dépendances MQTT.
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


class FakeDriver:
    def __init__(self):
        self.valve_open = False
        self.pump_running = False
        self.feedback_enabled = True

    def status(self):
        return {
            "valve_open": self.valve_open if self.feedback_enabled else False,
            "pump_running": self.pump_running if self.feedback_enabled else False,
        }


def controller_stub(driver_name="waveshare_modbus"):
    controller = GeoCoolingController.__new__(GeoCoolingController)
    controller.driver_name = driver_name
    controller.driver = FakeDriver()
    controller.hardware_sequence_enabled = False
    controller.sequence_verify_feedback = True
    controller.sequence_feedback_timeout_seconds = 0.05
    controller.sequence_feedback_poll_seconds = 0.005
    controller._lock = threading.RLock()
    return controller


def test_real_sequence_is_disabled_by_default():
    controller = controller_stub()
    allowed, reason = controller._hardware_sequence_allowed()
    assert allowed is False
    assert "GEOCOOLING_HARDWARE_SEQUENCE_ENABLED=true" in reason


def test_simulation_sequence_remains_allowed():
    controller = controller_stub("simulation")
    allowed, _ = controller._hardware_sequence_allowed()
    assert allowed is True


def test_real_sequence_can_be_explicitly_enabled():
    controller = controller_stub()
    controller.hardware_sequence_enabled = True
    allowed, _ = controller._hardware_sequence_allowed()
    assert allowed is True


def test_feedback_confirmation_accepts_expected_state():
    controller = controller_stub()
    controller.driver.valve_open = True
    result = controller._wait_for_actuator_state(
        valve_open=True,
        pump_running=False,
        action="test",
    )
    assert result["valve_open"] is True


def test_feedback_confirmation_rejects_incoherent_state():
    controller = controller_stub()
    with pytest.raises(RuntimeError, match="Confirmation matérielle absente"):
        controller._wait_for_actuator_state(
            valve_open=True,
            action="ouverture de la vanne",
        )


def test_feedback_can_be_disabled_for_simulated_clients():
    controller = controller_stub()
    controller.sequence_verify_feedback = False
    result = controller._wait_for_actuator_state(
        valve_open=True,
        action="test",
    )
    assert result["valve_open"] is False
