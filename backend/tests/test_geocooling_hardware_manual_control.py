from types import SimpleNamespace

import pytest

from app.geocooling.hardware_manual_control import (
    ARM_CONFIRMATION,
    HardwareManualControl,
)
from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver


class FakeClient:
    def __init__(self):
        self.coils = {}

    def read_coil(self, address):
        return bool(self.coils.get(address, False))

    def write_coil(self, address, enabled):
        self.coils[address] = bool(enabled)


def make_control(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "false")
    driver = WaveshareModbusDriver(client=FakeClient())
    controller = SimpleNamespace(
        driver=driver,
        driver_name="waveshare_modbus",
        mode=SimpleNamespace(value="MANUAL"),
        state=SimpleNamespace(value="OFF"),
    )
    return HardwareManualControl(controller), driver


def test_arm_requires_exact_confirmation(monkeypatch):
    control, driver = make_control(monkeypatch)
    with pytest.raises(ValueError):
        control.arm(confirmation="oui", requested_by="pytest")
    assert driver.armed is False


def test_manual_valve_and_pump_sequence(monkeypatch):
    control, driver = make_control(monkeypatch)
    control.arm(confirmation=ARM_CONFIRMATION, requested_by="pytest")
    control.valve_open(requested_by="pytest")
    control.pump_start(requested_by="pytest")
    status = control.status()
    assert status["armed"] is True
    assert status["valve_open"] is True
    assert status["pump_running"] is True


def test_valve_cannot_close_while_pump_runs(monkeypatch):
    control, _ = make_control(monkeypatch)
    control.arm(confirmation=ARM_CONFIRMATION, requested_by="pytest")
    control.valve_open(requested_by="pytest")
    control.pump_start(requested_by="pytest")
    with pytest.raises(RuntimeError, match="circulateur"):
        control.valve_close(requested_by="pytest")


def test_disarm_forces_safe_state(monkeypatch):
    control, _ = make_control(monkeypatch)
    control.arm(confirmation=ARM_CONFIRMATION, requested_by="pytest")
    control.valve_open(requested_by="pytest")
    control.pump_start(requested_by="pytest")
    status = control.disarm(requested_by="pytest")
    assert status["armed"] is False
    assert status["pump_running"] is False
    assert status["valve_open"] is False


def test_stop_actions_remain_available_when_disarmed(monkeypatch):
    control, driver = make_control(monkeypatch)
    driver.client.coils[driver.valve_address] = True
    driver.client.coils[driver.pump_address] = True
    status = control.safe_stop(requested_by="pytest")
    assert status["pump_running"] is False
    assert status["valve_open"] is False
