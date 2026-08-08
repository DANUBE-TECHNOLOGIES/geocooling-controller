from __future__ import annotations

import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActivationDecision:
    allowed: bool
    reason: str
    certification_passed: bool
    explicit_activation: bool
    real_driver: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "certification_passed": self.certification_passed,
            "explicit_activation": self.explicit_activation,
            "real_driver": self.real_driver,
        }


class ControllerActivationGuard:
    """Fail-closed gate protecting automatic real-hardware execution.

    F2 introduces two independent protections before the controller may
    automatically sequence real hardware:

    1. the latest field certification must be PASS;
    2. real automatic execution must be explicitly activated by configuration.

    Simulation is intentionally unaffected. A certification never activates
    hardware by itself.
    """

    VERSION = "F2-CONTROLLER-ACTIVATION-GUARD-1.0"

    def __init__(self, field_certification: Any | None = None) -> None:
        self.field_certification = field_certification

    @staticmethod
    def _env_enabled(name: str) -> bool:
        return os.getenv(name, "false").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    def _certification_passed(self) -> bool:
        service = self.field_certification
        if service is None:
            return False

        try:
            status = service.status()
        except Exception:
            return False

        if not isinstance(status, dict):
            return False

        certificate = status.get("last_certificate")
        return bool(
            status.get("certified") is True
            and isinstance(certificate, dict)
            and certificate.get("status") == "PASS"
        )

    def evaluate(self, *, driver_name: str) -> ActivationDecision:
        real_driver = driver_name.strip().lower() != "simulation"

        if not real_driver:
            return ActivationDecision(
                allowed=True,
                reason="Simulation autorisée sans activation matérielle.",
                certification_passed=False,
                explicit_activation=False,
                real_driver=False,
            )

        certification_passed = self._certification_passed()
        explicit_activation = self._env_enabled(
            "GEOCOOLING_REAL_AUTOMATIC_EXECUTION_ENABLED"
        )

        if not certification_passed:
            return ActivationDecision(
                allowed=False,
                reason=(
                    "Exécution automatique matérielle interdite : "
                    "certification terrain PASS requise."
                ),
                certification_passed=False,
                explicit_activation=explicit_activation,
                real_driver=True,
            )

        if not explicit_activation:
            return ActivationDecision(
                allowed=False,
                reason=(
                    "Exécution automatique matérielle interdite : "
                    "activation explicite absente."
                ),
                certification_passed=True,
                explicit_activation=False,
                real_driver=True,
            )

        return ActivationDecision(
            allowed=True,
            reason=(
                "Certification terrain PASS et activation explicite validées."
            ),
            certification_passed=True,
            explicit_activation=True,
            real_driver=True,
        )

    def status(self, *, driver_name: str) -> dict[str, Any]:
        decision = self.evaluate(driver_name=driver_name)
        return {
            "version": self.VERSION,
            **decision.as_dict(),
            "fail_closed": True,
            "certification_does_not_activate_hardware": True,
        }
