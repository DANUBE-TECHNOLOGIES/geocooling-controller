"""Fail-closed policy gate for arbitrary Waveshare relay activation.

The public diagnostic endpoint ``/geocooling/relay/{id}/on`` reaches
``WaveshareModbusDriver.set_relay`` directly.  This patch prevents that low-level
path from bypassing commissioning.  Generic relay OFF remains always available.
Dedicated EV / M11+M13 commissioning methods are intentionally unaffected.
"""

from __future__ import annotations

from typing import Any, Callable

from app.geocooling.commissioning_readiness_service import (
    CommissioningReadinessService,
)
from app.geocooling.hardware_activation_policy import (
    build_hardware_activation_policy,
)
from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver


_PATCH_MARKER = "_direct_relay_policy_gate_installed"


def _readiness(driver: WaveshareModbusDriver) -> dict[str, Any]:
    provider = getattr(driver, "direct_relay_readiness_provider", None)
    if callable(provider):
        result = provider()
    else:
        result = CommissioningReadinessService().status()
    if not isinstance(result, dict):
        raise RuntimeError("Commissioning readiness invalide.")
    return result


def install_direct_relay_policy_gate() -> None:
    cls = WaveshareModbusDriver
    if getattr(cls, _PATCH_MARKER, False):
        return

    original: Callable[[WaveshareModbusDriver, int, bool], None] = cls.set_relay

    def gated_set_relay(
        self: WaveshareModbusDriver,
        relay_id: int,
        enabled: bool,
    ) -> None:
        requested = bool(enabled)

        # Preserve the driver's existing, more immediate disarmed error.
        if requested and not bool(getattr(self, "armed", False)):
            return original(self, relay_id, requested)

        if requested:
            try:
                readiness = _readiness(self)
                policy = build_hardware_activation_policy(readiness)
            except Exception as exc:
                raise RuntimeError(
                    "Activation relais refusée : commissioning gate indisponible."
                ) from exc

            if not bool(policy.get("manual_positive_commands_allowed", False)):
                state = str(policy.get("readiness_state") or "UNKNOWN")
                raise RuntimeError(
                    "Activation relais arbitraire refusée par le Commissioning Gate : "
                    f"état {state}. READY_FOR_RELEASE est requis."
                )

        return original(self, relay_id, requested)

    cls.set_relay = gated_set_relay  # type: ignore[method-assign]
    setattr(cls, _PATCH_MARKER, True)
