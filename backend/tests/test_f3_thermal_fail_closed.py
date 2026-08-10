import sys
import threading
import types
from datetime import timedelta

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

from app.geocooling.controller import GeoCoolingController, utc_now
from app.geocooling.models import GeoCoolingState
from app.geocooling.safety import GeoCoolingSafetyManager
from app.geocooling.thermal import ThermalSnapshot


class ThermalEngineStub:
    def __init__(self, latest=None):
        self._latest = latest

    def latest(self):
        return self._latest


class DriverStub:
    def __init__(self):
        self.valve_open = False
        self.pump_running = False
        self.start_pump_calls = 0

    def open_valve(self):
        self.valve_open = True

    def start_pump(self):
        self.start_pump_calls += 1
        self.pump_running = True

    def force_safe_state(self):
        self.pump_running = False
        self.valve_open = False


class DeviceManagerStub:
    def status(self):
        return {"ready": True, "reason": "ready"}


def controller_with_snapshot(snapshot):
    controller = GeoCoolingController.__new__(GeoCoolingController)
    controller.driver_name = "waveshare_modbus"
    controller.thermal_engine = ThermalEngineStub(snapshot)
    controller.safety_manager = GeoCoolingSafetyManager()
    return controller


def test_real_driver_blocks_when_no_thermal_snapshot_exists(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "180")
    controller = controller_with_snapshot(None)

    result = controller._thermal_safety()

    assert result["safe"] is False
    assert result["level"] == "blocked"
    assert result["required"] is True


def test_real_driver_blocks_incomplete_thermal_snapshot_by_default(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "180")
    monkeypatch.delenv("GEOCOOLING_SURFACE_REFERENCE_MODE", raising=False)
    snapshot = ThermalSnapshot(
        timestamp=utc_now(),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=55.0,
        surface_temperature_c=None,
        floor_supply_temperature_c=18.0,
        floor_return_temperature_c=20.0,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is False
    assert result["level"] == "blocked"
    assert "référence de surface" in result["reason"]


def test_real_driver_accepts_explicit_floor_loop_surface_estimate(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "180")
    monkeypatch.setenv("GEOCOOLING_SURFACE_REFERENCE_MODE", "floor_loop_estimate")
    monkeypatch.setenv("GEOCOOLING_SURFACE_ESTIMATION_BIAS_C", "-0.5")
    snapshot = ThermalSnapshot(
        timestamp=utc_now(),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=50.0,
        surface_temperature_c=None,
        floor_supply_temperature_c=18.0,
        floor_return_temperature_c=20.0,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is True
    assert result["surface_estimated"] is True
    assert result["surface_reference_mode"] == "floor_loop_estimate"
    assert result["surface_temperature_c"] == 18.5
    assert result["surface_estimation"]["mean_water_temperature_c"] == 19.0


def test_real_driver_estimated_surface_fails_closed_if_return_missing(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_SURFACE_REFERENCE_MODE", "floor_loop_estimate")
    snapshot = ThermalSnapshot(
        timestamp=utc_now(),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=50.0,
        surface_temperature_c=None,
        floor_supply_temperature_c=18.0,
        floor_return_temperature_c=None,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is False
    assert result["level"] == "blocked"
    assert result["surface_estimated"] is False


def test_real_driver_blocks_stale_thermal_snapshot(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "60")
    snapshot = ThermalSnapshot(
        timestamp=utc_now() - timedelta(seconds=61),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=55.0,
        surface_temperature_c=22.0,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is False
    assert result["level"] == "stale"
    assert result["fresh"] is False


def test_real_driver_accepts_fresh_snapshot_with_safe_dew_point_margin(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "180")
    snapshot = ThermalSnapshot(
        timestamp=utc_now(),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=50.0,
        surface_temperature_c=22.0,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is True
    assert result["level"] == "safe"
    assert result["fresh"] is True
    assert result["margin_c"] >= controller.safety_manager.minimum_margin_c


def test_real_driver_blocks_fresh_snapshot_with_condensation_risk(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_THERMAL_MAX_AGE_SECONDS", "180")
    snapshot = ThermalSnapshot(
        timestamp=utc_now(),
        indoor_temperature_c=26.0,
        indoor_humidity_percent=70.0,
        surface_temperature_c=20.0,
    )
    controller = controller_with_snapshot(snapshot)

    result = controller._thermal_safety()

    assert result["safe"] is False
    assert result["level"] == "condensation_risk"


def test_sensor_loss_while_running_requests_safe_stop():
    controller = GeoCoolingController.__new__(GeoCoolingController)
    controller._lock = threading.RLock()
    controller.driver_name = "waveshare_modbus"
    controller.driver = DriverStub()
    controller.device_manager = DeviceManagerStub()
    controller.state = GeoCoolingState.OFF
    controller.valve_open_delay = 0.0
    controller.watchdog_interval_seconds = 0.01
    controller.max_runtime_seconds = 7200
    controller.started_at = None
    controller.stopped_at = None
    controller.cycle_count = 0
    controller.last_error = None

    transitions = []
    safe_stop_reasons = []
    safety_results = iter(
        [
            {"safe": True, "reason": "fresh"},
            {
                "safe": False,
                "level": "stale",
                "reason": "données thermiques périmées",
            },
        ]
    )

    def transition(new_state, event_type, reason):
        controller.state = new_state
        transitions.append(new_state)

    class StopEventStub:
        def wait(self, timeout=None):
            return False

    controller._transition = transition
    controller._wait_for_actuator_state = lambda **kwargs: {}
    controller._interruptible_wait = lambda seconds: False
    controller._thermal_safety = lambda: next(safety_results)
    controller._safe_stop_sequence = safe_stop_reasons.append
    controller._runtime_seconds = lambda: 0
    controller._stop_request = StopEventStub()

    controller._start_sequence()

    assert GeoCoolingState.RUNNING in transitions
    assert controller.driver.start_pump_calls == 1
    assert safe_stop_reasons == ["Arrêt de sécurité anti-condensation"]
    assert "périmées" in controller.last_error
