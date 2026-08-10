from app.geocooling.commissioning_test_manager import (
    CONFIRMATION_TEXT,
    GeoCoolingCommissioningTestManager,
)


class FakeDriver:
    def open_valve(self):
        pass

    def close_valve(self):
        pass

    def start_pump(self):
        pass

    def stop_pump(self):
        pass

    def status(self):
        return {"ready": True}


class FakeController:
    def __init__(self, *, simulation: bool):
        self.driver = FakeDriver()
        self.driver_name = "simulation" if simulation else "waveshare_modbus"
        self.autopilot_enabled = False
        self.valve_open_delay = 0.0
        self.valve_close_delay = 0.0
        self._simulation = simulation

    def status(self):
        return {
            "state": "OFF",
            "mode": "MANUAL",
            "driver_name": self.driver_name,
            "simulation": self._simulation,
            "device": {"ready": True},
        }

    def autopilot_status(self):
        return {"enabled": False}


def manager(*, simulation: bool) -> GeoCoolingCommissioningTestManager:
    result = GeoCoolingCommissioningTestManager(FakeController(simulation=simulation))
    result.real_tests_enabled = True
    return result


def test_physical_commissioning_test_is_blocked_before_field_window():
    subject = manager(simulation=False)
    subject.commissioning_readiness_provider = lambda: {
        "state": "MAPPING_INCOMPLETE"
    }

    try:
        subject._validate_request(
            target="valve",
            duration_seconds=1,
            confirmation=CONFIRMATION_TEXT,
        )
    except RuntimeError as exc:
        assert "Commissioning Gate" in str(exc)
        assert "MAPPING_INCOMPLETE" in str(exc)
    else:
        raise AssertionError("physical test should have been blocked")


def test_physical_commissioning_test_is_allowed_in_field_window():
    subject = manager(simulation=False)
    subject.commissioning_readiness_provider = lambda: {
        "state": "FIELD_CERTIFICATION_REQUIRED"
    }

    result = subject._validate_request(
        target="valve",
        duration_seconds=1,
        confirmation=CONFIRMATION_TEXT,
    )

    assert result["simulation"] is False
    assert result["commissioning_policy_checked"] is True


def test_physical_commissioning_gate_fails_closed_when_provider_errors():
    subject = manager(simulation=False)

    def broken():
        raise RuntimeError("database unavailable")

    subject.commissioning_readiness_provider = broken

    try:
        subject._validate_request(
            target="pump",
            duration_seconds=1,
            confirmation=CONFIRMATION_TEXT,
        )
    except RuntimeError as exc:
        assert "gate indisponible" in str(exc)
    else:
        raise AssertionError("physical test should fail closed")


def test_simulation_does_not_depend_on_commissioning_readiness():
    subject = manager(simulation=True)

    def broken():
        raise RuntimeError("must not be called")

    subject.commissioning_readiness_provider = broken

    result = subject._validate_request(
        target="pump",
        duration_seconds=1,
        confirmation=None,
    )

    assert result["simulation"] is True
    assert result["commissioning_policy_checked"] is False
