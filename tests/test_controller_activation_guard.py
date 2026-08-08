from app.geocooling.controller_activation_guard import ControllerActivationGuard


class Certification:
    def __init__(self, passed: bool):
        self.passed = passed

    def status(self):
        certificate = {"status": "PASS" if self.passed else "FAIL"}
        return {
            "certified": self.passed,
            "last_certificate": certificate,
        }


def test_simulation_remains_allowed_without_certificate(monkeypatch):
    monkeypatch.delenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", raising=False)
    decision = ControllerActivationGuard().evaluate(driver_name="simulation")
    assert decision.allowed is True
    assert decision.real_driver is False


def test_real_driver_fails_closed_without_certification(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", "true")
    decision = ControllerActivationGuard().evaluate(driver_name="waveshare_modbus")
    assert decision.allowed is False
    assert decision.certification_passed is False
    assert decision.explicit_activation is True


def test_certificate_alone_never_activates_real_hardware(monkeypatch):
    monkeypatch.delenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", raising=False)
    decision = ControllerActivationGuard(Certification(True)).evaluate(
        driver_name="waveshare_modbus"
    )
    assert decision.allowed is False
    assert decision.certification_passed is True
    assert decision.explicit_activation is False


def test_explicit_activation_alone_is_not_enough(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", "true")
    decision = ControllerActivationGuard(Certification(False)).evaluate(
        driver_name="waveshare_modbus"
    )
    assert decision.allowed is False


def test_real_automatic_execution_requires_both_protections(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", "true")
    decision = ControllerActivationGuard(Certification(True)).evaluate(
        driver_name="waveshare_modbus"
    )
    assert decision.allowed is True
    assert decision.certification_passed is True
    assert decision.explicit_activation is True


def test_status_documents_fail_closed_contract(monkeypatch):
    monkeypatch.delenv("GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED", raising=False)
    status = ControllerActivationGuard(Certification(True)).status(
        driver_name="waveshare_modbus"
    )
    assert status["fail_closed"] is True
    assert status["certification_does_not_activate_hardware"] is True
