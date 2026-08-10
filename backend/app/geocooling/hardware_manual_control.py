"""Pilotage matériel manuel sécurisé du GeoCooling."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Callable

from app.geocooling.commissioning_readiness_service import CommissioningReadinessService

ARM_CONFIRMATION = "J'ARME LE GEOCOOLING"


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class HardwareManualControl:
    """Façade API pour les opérations directes sur les actionneurs.

    Les commandes d'activation nécessitent un pilote Waveshare armé et un état
    de commissioning compatible. Les commandes d'arrêt restent toujours
    disponibles afin de préserver le repli vers l'état sûr.
    """

    def __init__(
        self,
        controller: Any,
        readiness_provider: Callable[[], dict[str, Any]] | None = None,
    ) -> None:
        self.controller = controller
        self.last_action: dict[str, Any] | None = None
        self._readiness_provider = readiness_provider

    @property
    def driver(self) -> Any:
        return self.controller.driver

    def _require_waveshare(self) -> None:
        if getattr(self.controller, "driver_name", "") != "waveshare_modbus":
            raise RuntimeError(
                "Le pilotage matériel direct exige GEOCOOLING_DRIVER=waveshare_modbus."
            )

    def _commissioning_status(self) -> dict[str, Any]:
        try:
            if self._readiness_provider is not None:
                status = self._readiness_provider()
            else:
                status = CommissioningReadinessService().status()
        except Exception as exc:
            raise RuntimeError(
                "Commande matérielle refusée : état de commissioning indisponible."
            ) from exc

        if not isinstance(status, dict):
            raise RuntimeError(
                "Commande matérielle refusée : état de commissioning invalide."
            )
        return status

    def _require_arm_stage(self) -> dict[str, Any]:
        status = self._commissioning_status()
        state = str(status.get("state") or "UNKNOWN")
        if state not in {"FIELD_CERTIFICATION_REQUIRED", "READY_FOR_RELEASE"}:
            raise RuntimeError(
                "Armement refusé : le commissioning doit avoir atteint "
                "FIELD_CERTIFICATION_REQUIRED. "
                f"État actuel : {state}."
            )
        return status

    def _require_release_ready(self, action: str) -> dict[str, Any]:
        status = self._commissioning_status()
        state = str(status.get("state") or "UNKNOWN")
        if state != "READY_FOR_RELEASE":
            raise RuntimeError(
                f"Commande {action} refusée : commissioning non certifié pour "
                f"l'exploitation réelle (état : {state})."
            )
        return status

    def _record(self, action: str, requested_by: str) -> None:
        self.last_action = {
            "action": action,
            "requested_by": requested_by,
            "at": utc_iso(),
        }

    def status(self) -> dict[str, Any]:
        driver_status = self.driver.status()
        try:
            commissioning = self._commissioning_status()
        except RuntimeError as exc:
            commissioning = {
                "state": "UNAVAILABLE",
                "ready_for_release": False,
                "error": str(exc),
            }
        return {
            "component": "geocooling",
            "view": "manual_hardware_control",
            "driver_name": getattr(self.controller, "driver_name", None),
            "armed": bool(driver_status.get("armed", False)),
            "connected": bool(driver_status.get("connected", False)),
            "ready": bool(driver_status.get("ready", False)),
            "valve_open": bool(driver_status.get("valve_open", False)),
            "pump_running": bool(driver_status.get("pump_running", False)),
            "controller": {
                "mode": self.controller.mode.value,
                "state": self.controller.state.value,
            },
            "commissioning": {
                "state": commissioning.get("state"),
                "ready_for_release": bool(
                    commissioning.get("ready_for_release", False)
                ),
            },
            "last_action": self.last_action,
            "driver": driver_status,
        }

    def arm(self, *, confirmation: str, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self._require_arm_stage()
        if confirmation.strip() != ARM_CONFIRMATION:
            raise ValueError(
                f"Confirmation invalide. Valeur requise : {ARM_CONFIRMATION}"
            )
        self.driver.set_armed(True)
        self._record("ARM", requested_by)
        return self.status()

    def disarm(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self.driver.set_armed(False)
        self._record("DISARM", requested_by)
        return self.status()

    def valve_open(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self._require_release_ready("VALVE_OPEN")
        self.driver.open_valve()
        self._record("VALVE_OPEN", requested_by)
        return self.status()

    def valve_close(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        if bool(self.driver.status().get("pump_running", False)):
            raise RuntimeError(
                "Fermeture de vanne refusée : arrêter d'abord le circulateur."
            )
        self.driver.close_valve()
        self._record("VALVE_CLOSE", requested_by)
        return self.status()

    def pump_start(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self._require_release_ready("PUMP_START")
        self.driver.start_pump()
        self._record("PUMP_START", requested_by)
        return self.status()

    def pump_stop(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self.driver.stop_pump()
        self._record("PUMP_STOP", requested_by)
        return self.status()

    def safe_stop(self, *, requested_by: str) -> dict[str, Any]:
        self._require_waveshare()
        self.driver.force_safe_state()
        self._record("SAFE_STOP", requested_by)
        return self.status()
