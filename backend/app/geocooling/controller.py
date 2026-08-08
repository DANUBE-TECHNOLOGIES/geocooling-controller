"""F2 hydraulic hardening wrapper for the GeoCooling controller.

The historical controller implementation is preserved in ``controller_base``.
This wrapper narrows the certified hydraulic behaviour without reopening the
large legacy module during finalization:

- START is accepted only from OFF (FAULT requires an explicit reset),
- thermal safety is re-evaluated immediately before M11+M13 are energized,
- every sequence failure enters FAULT deterministically after a best-effort
  safe-state rollback.
"""

from __future__ import annotations

import logging

from app.geocooling.controller_base import (
    GeoCoolingController as _BaseGeoCoolingController,
    utc_now,
)
from app.geocooling.models import GeoCoolingState

logger = logging.getLogger("sbc.geocooling")


class GeoCoolingController(_BaseGeoCoolingController):
    """Certified F2 controller behaviour layered on the legacy controller."""

    def _enter_fault(
        self,
        reason: str,
        *,
        event_type: str = "geocooling.fault",
    ) -> None:
        """Enter FAULT even when the hardware rollback itself encounters errors."""

        safe_state_error: str | None = None

        try:
            self.driver.force_safe_state()
        except Exception as exc:  # pragma: no cover - hardware dependent
            safe_state_error = str(exc)
            logger.critical(
                "F2 rollback matériel incomplet pendant l'entrée en FAULT: %s",
                exc,
                exc_info=True,
            )

        final_reason = str(reason)
        if safe_state_error:
            final_reason = (
                f"{final_reason} | repli état sûr incomplet: {safe_state_error}"
            )

        self.last_error = final_reason
        self.stopped_at = utc_now()

        # _transition sets the in-memory state before persistence. Therefore,
        # even a later telemetry/persistence failure cannot leave the state as
        # RUNNING/STARTING after a sequence fault.
        try:
            self._transition(
                GeoCoolingState.FAULT,
                event_type,
                final_reason,
            )
        except Exception:
            with self._lock:
                self.state = GeoCoolingState.FAULT
                self.state_changed_at = utc_now()
                self.last_event = event_type
                self.last_reason = final_reason
            logger.exception(
                "Échec de persistance de l'état FAULT; état mémoire forcé."
            )

    def request_start(self) -> dict[str, object]:
        """Reject any START unless the controller is explicitly OFF."""

        with self._lock:
            if self.state == GeoCoolingState.FAULT:
                return {
                    "accepted": False,
                    "message": (
                        "Démarrage refusé : le contrôleur est en FAULT. "
                        "Un reset explicite est obligatoire avant tout redémarrage."
                    ),
                    "status": self.status(),
                }

            if self.state == GeoCoolingState.EMERGENCY_STOP:
                return {
                    "accepted": False,
                    "message": (
                        "Démarrage refusé : arrêt d'urgence actif. "
                        "Un reset explicite est obligatoire avant tout redémarrage."
                    ),
                    "status": self.status(),
                }

            if self.state != GeoCoolingState.OFF:
                return {
                    "accepted": False,
                    "message": (
                        "Démarrage refusé : le contrôleur doit être OFF "
                        f"(état actuel : {self.state.value})."
                    ),
                    "status": self.status(),
                }

        return super().request_start()

    def _start_sequence(self) -> None:
        try:
            self._transition(
                GeoCoolingState.OPENING_VALVE,
                "geocooling.valve_opening",
                "Commande d'ouverture de l'électrovanne EV",
            )

            self.driver.open_valve()
            self._wait_for_actuator_state(
                valve_open=True,
                pump_running=False,
                action="ouverture de l'EV",
            )

            self._transition(
                GeoCoolingState.WAITING_FLOW,
                "geocooling.waiting_flow",
                "Temporisation après ouverture de l'électrovanne EV",
            )

            if self._interruptible_wait(self.valve_open_delay):
                self._safe_stop_sequence(
                    "Démarrage interrompu par une demande d'arrêt"
                )
                return

            # F2: the initial START safety check is not enough. Conditions may
            # change during valve opening / hydraulic delay, so condensation
            # safety is checked again immediately before M11+M13 are energized.
            thermal_safety = self._thermal_safety()
            if not bool(thermal_safety.get("safe", False)):
                reason = str(
                    thermal_safety.get(
                        "reason",
                        "Sécurité thermique non satisfaite avant M11+M13",
                    )
                )
                self.last_error = reason
                self._safe_stop_sequence(
                    "Démarrage interrompu avant M11+M13 : " + reason
                )
                return

            self._transition(
                GeoCoolingState.STARTING_PUMP,
                "geocooling.pump_starting",
                "Commande de démarrage du groupe M11+M13",
            )

            self.driver.start_pump()
            self._wait_for_actuator_state(
                valve_open=True,
                pump_running=True,
                action="démarrage de M11+M13",
            )

            with self._lock:
                self.started_at = utc_now()
                self.stopped_at = None
                self.cycle_count += 1

            self._transition(
                GeoCoolingState.RUNNING,
                "geocooling.running",
                "GeoCooling en fonctionnement",
            )

            while not self._stop_request.wait(
                timeout=self.watchdog_interval_seconds
            ):
                device_status = self.device_manager.status()
                if not bool(device_status.get("ready", False)):
                    self._enter_fault(
                        "Watchdog matériel : "
                        + str(
                            device_status.get(
                                "reason",
                                "matériel indisponible",
                            )
                        ),
                        event_type="geocooling.watchdog_fault",
                    )
                    return

                thermal_safety = self._thermal_safety()
                if not bool(thermal_safety.get("safe", False)):
                    self.last_error = str(
                        thermal_safety.get(
                            "reason",
                            "Sécurité thermique non satisfaite",
                        )
                    )
                    self._safe_stop_sequence(
                        "Arrêt de sécurité anti-condensation"
                    )
                    return

                if self._runtime_seconds() >= self.max_runtime_seconds:
                    self._safe_stop_sequence(
                        "Durée maximale de fonctionnement atteinte"
                    )
                    return

            with self._lock:
                emergency_active = (
                    self.state == GeoCoolingState.EMERGENCY_STOP
                )

            if emergency_active:
                return

            self._safe_stop_sequence("Arrêt manuel demandé")

        except Exception as exc:
            logger.exception(
                "Défaut pendant la séquence de démarrage GeoCooling"
            )
            self._enter_fault(str(exc))

    def _safe_stop_sequence(self, reason: str) -> None:
        try:
            self._transition(
                GeoCoolingState.STOPPING_PUMP,
                "geocooling.pump_stopping",
                reason,
            )

            self.driver.stop_pump()
            self._wait_for_actuator_state(
                pump_running=False,
                action="arrêt de M11+M13",
            )

            self._transition(
                GeoCoolingState.WAITING_DRAIN,
                "geocooling.waiting_drain",
                "Temporisation avant fermeture de l'électrovanne EV",
            )

            # Keep the historical non-interruptible drain delay: once stopping
            # has begun, the certified order is M11+M13 OFF then EV CLOSED.
            import time

            time.sleep(self.valve_close_delay)

            self._transition(
                GeoCoolingState.CLOSING_VALVE,
                "geocooling.valve_closing",
                "Commande de fermeture de l'électrovanne EV",
            )

            self.driver.close_valve()
            self._wait_for_actuator_state(
                valve_open=False,
                pump_running=False,
                action="fermeture de l'EV",
            )

            with self._lock:
                self.stopped_at = utc_now()

            self._transition(
                GeoCoolingState.OFF,
                "geocooling.stopped",
                "GeoCooling arrêté en sécurité",
            )

            self._stop_request.clear()

        except Exception as exc:
            logger.exception(
                "Défaut pendant la séquence d'arrêt GeoCooling"
            )
            self._enter_fault(str(exc))
