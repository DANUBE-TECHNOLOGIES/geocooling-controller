"""Fail-closed commissioning gate for physical actuator tests.

This module installs a narrow wrapper around
``GeoCoolingCommissioningTestManager._validate_request``.  Simulation remains
unchanged.  A physical test is accepted only when the central hardware
activation policy explicitly opens the commissioning-test window.
"""

from __future__ import annotations

from typing import Any, Callable

from app.geocooling.commissioning_readiness_service import (
    CommissioningReadinessService,
)
from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)
from app.geocooling.commissioning_test_manager import (
    GeoCoolingCommissioningTestManager,
)


_PATCH_MARKER = "_commissioning_policy_gate_installed"


def _readiness(manager: GeoCoolingCommissioningTestManager) -> dict[str, Any]:
    provider = getattr(manager, "commissioning_readiness_provider", None)
    if callable(provider):
        result = provider()
    else:
        result = CommissioningReadinessService().status()

    if not isinstance(result, dict):
        raise RuntimeError("Commissioning readiness invalide.")
    return result


def install_commissioning_test_policy_gate() -> None:
    """Install the gate once for all manager instances."""

    cls = GeoCoolingCommissioningTestManager
    if getattr(cls, _PATCH_MARKER, False):
        return

    original: Callable[..., dict[str, Any]] = cls._validate_request

    def gated_validate_request(
        self: GeoCoolingCommissioningTestManager,
        *,
        target: str,
        duration_seconds: int,
        confirmation: str | None,
    ) -> dict[str, Any]:
        controller_status = self._controller_status()
        simulation = self._simulation(controller_status)

        if not simulation:
            try:
                readiness = _readiness(self)
                policy = build_hardware_activation_policy(readiness)
            except Exception as exc:
                raise RuntimeError(
                    "Test physique refusé : commissioning gate indisponible."
                ) from exc

            if not bool(policy.get("commissioning_tests_allowed", False)):
                state = str(policy.get("readiness_state") or "UNKNOWN")
                raise RuntimeError(
                    "Test physique refusé par le Commissioning Gate : "
                    f"état {state}. Le niveau FIELD_CERTIFICATION_REQUIRED "
                    "doit être atteint avant tout essai EV / M11+M13."
                )

        result = original(
            self,
            target=target,
            duration_seconds=duration_seconds,
            confirmation=confirmation,
        )

        if not isinstance(result, dict):
            raise RuntimeError("Validation commissioning invalide.")

        return {
            **result,
            "commissioning_policy_checked": not simulation,
        }

    cls._validate_request = gated_validate_request  # type: ignore[method-assign]
    setattr(cls, _PATCH_MARKER, True)
