from types import SimpleNamespace

import pytest

from app.geocooling.hardware_manual_control import (
    ARM_CONFIRMATION,
    HardwareManualControl,
)


class FakeDriver:
    def __init__(self) -> None:
        self.armed = False
        self.valve_open_state = False
        self.pump_running = False
        self.safe_stop_calls = 0

    def status(self):
        return {
            "armed": self.armed,
            "connected": True,
            "ready": True,
            "valve_open": self.valve_open_state,
            "pump_running": self.pump_running,
        }

    def set_armed(self, value: bool):
        self.armed = bool(value)

    def open_valve(self):
        self.valve_open_state = True

    def close_valve(self):
        self.valve_open_state = False

    def start_pump(self):
        self.pump_running = True

    def stop_pump(self):
        self.pump_running = False

    def force_safe_state(self):
        self.safe_stop_calls += 1
        self.pump_running = False
        self.valve_open_state = False


def controller_with(driver: FakeDriver):
    return SimpleNamespace(
        driver=driver,
        driver_name="waveshare_modbus",
        mode=SimpleNamespace(value="manual"),
        state=SimpleNamespace(value="OFF"),
    )


def readiness(state: str):
    return lambda: {
        "state": state,
        "ready_for_release": state == "READY_FOR_RELEASE",
    }


def test_arm_is_refused_before_field_certification_stage():
    driver = FakeDriver()
    control = HardwareManualControl(
        controller_with(driver),
        readiness_provider=readiness("MAPPING_INCOMPLETE"),
    )

    with pytest.raises(RuntimeError, match="FIELD_CERTIFICATION_REQUIRED"):
        control.arm(
            confirmation=ARM_CONFIRMATION,
            requested_by="test",
        )

    assert driver.armed is False


def test_arm_is_allowed_for_field_certification_stage():
    driver = FakeDriver()
    control = HardwareManualControl(
        controller_with(driver),
        readiness_provider=readiness("FIELD_CERTIFICATION_REQUIRED"),
    )

    result = control.arm(
        confirmation=ARM_CONFIRMATION,
        requested_by="test",
    )

    assert driver.armed is True
    assert result["commissioning"]["state"] == "FIELD_CERTIFICATION_REQUIRED"


def test_manual_positive_commands_are_blocked_until_release_ready():
    driver = FakeDriver()
    driver.armed = True
    control = HardwareManualControl(
        controller_with(driver),
        readiness_provider=readiness("FIELD_CERTIFICATION_REQUIRED"),
    )

    with pytest.raises(RuntimeError, match="commissioning non certifié"):
        control.valve_open(requested_by="test")

    with pytest.raises(RuntimeError, match="commissioning non certifié"):
        control.pump_start(requested_by="test")

    assert driver.valve_open_state is False
    assert driver.pump_running is False


def test_manual_positive_commands_are_allowed_after_release_ready():
    driver = FakeDriver()
    driver.armed = True
    control = HardwareManualControl(
        controller_with(driver),
        readiness_provider=readiness("READY_FOR_RELEASE"),
    )

    control.valve_open(requested_by="test")
    control.pump_start(requested_by="test")

    assert driver.valve_open_state is True
    assert driver.pump_running is True


def test_safe_commands_remain_available_when_gate_is_not_ready():
    driver = FakeDriver()
    driver.armed = True
    driver.valve_open_state = True
    driver.pump_running = True
    control = HardwareManualControl(
        controller_with(driver),
        readiness_provider=readiness("UPSTREAM_NOT_READY"),
    )

    control.pump_stop(requested_by="test")
    control.valve_close(requested_by="test")
    control.safe_stop(requested_by="test")
    control.disarm(requested_by="test")

    assert driver.pump_running is False
    assert driver.valve_open_state is False
    assert driver.safe_stop_calls == 1
    assert driver.armed is False
