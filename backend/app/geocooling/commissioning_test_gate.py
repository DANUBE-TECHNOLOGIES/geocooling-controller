"""Fail-closed gate for GeoCooling physical commissioning tests."""

from __future__ import annotations

from typing import Any, Callable, Mapping

from app.geocooling.hardware_activation_policy import build_hardware_activation_policy


class CommissioningTestGateError(RuntimeError):
    """Raised when a physical commissioning test is outside its allowed window."""


def validate_commissioning_test_readiness(
    readiness: Mapping[str, Any],
) -> dict[str, Any]:
    """Validate the commissioning state without touching hardware.

    Physical tests are intentionally allowed only once the field-certification
    stage has been reached. Unknown or malformed readiness reports fail closed.
    """

    policy = build_hardware_activation_policy(readiness)
    state = str(policy.get("readiness_state") or "UNKNOWN")

    if not bool(policy.get("commissioning_tests_allowed", False)):
        raise CommissioningTestGateError(
            "Test physique de commissioning refusé : "
            f"état de mise en service {state}. "
            "La fenêtre minimale requise est FIELD_CERTIFICATION_REQUIRED."
        )

    return {
        "allowed": True,
        "readiness_state": state,
        "policy": policy,
        "read_only": True,
        "hardware_touched": False,
    }


def validate_commissioning_test_with_provider(
    readiness_provider: Callable[[], Mapping[str, Any]],
) -> dict[str, Any]:
    """Resolve readiness at request time and fail closed on provider errors."""

    try:
        readiness = readiness_provider()
    except Exception as exc:
        raise CommissioningTestGateError(
            "Test physique de commissioning refusé : "
            "impossible de déterminer l'état de mise en service."
        ) from exc

    if not isinstance(readiness, Mapping):
        raise CommissioningTestGateError(
            "Test physique de commissioning refusé : "
            "rapport de mise en service invalide."
        )

    return validate_commissioning_test_readiness(readiness)
