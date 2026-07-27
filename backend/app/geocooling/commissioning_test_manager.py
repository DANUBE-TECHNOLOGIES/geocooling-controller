"""Tests temporisés et sécurisés des actionneurs GeoCooling.

Ce module est exclusivement destiné à la mise en service.

Les tests réels sont désactivés par défaut. Pour les autoriser avec le pilote
MQTT réel, la variable suivante doit être explicitement configurée :

    GEOCOOLING_COMMISSIONING_TESTS_ENABLED=true

Une confirmation exacte reste obligatoire pour chaque demande :

    JE CONFIRME LE TEST GEOCOOLING
"""

from __future__ import annotations

import logging
import os
import threading
import time
import uuid
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(
    "sbc.geocooling.commissioning"
)


CONFIRMATION_TEXT = (
    "JE CONFIRME LE TEST GEOCOOLING"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_or_none(
    value: datetime | None,
) -> str | None:
    if value is None:
        return None

    return value.isoformat()


def env_bool(
    name: str,
    default: bool = False,
) -> bool:
    raw = os.getenv(
        name,
        "true" if default else "false",
    )

    return raw.strip().lower() in {
        "1",
        "true",
        "yes",
        "on",
    }


class GeoCoolingCommissioningTestManager:
    """Pilote des tests temporisés avec interverrouillages."""

    def __init__(
        self,
        controller: Any,
    ) -> None:
        self.controller = controller

        self.real_tests_enabled = env_bool(
            "GEOCOOLING_COMMISSIONING_TESTS_ENABLED",
            False,
        )

        self.minimum_duration_seconds = max(
            1,
            int(
                os.getenv(
                    "GEOCOOLING_COMMISSIONING_MIN_TEST_SECONDS",
                    "1",
                )
            ),
        )

        self.maximum_duration_seconds = max(
            self.minimum_duration_seconds,
            min(
                10,
                int(
                    os.getenv(
                        "GEOCOOLING_COMMISSIONING_MAX_TEST_SECONDS",
                        "10",
                    )
                ),
            ),
        )

        self.default_duration_seconds = min(
            self.maximum_duration_seconds,
            max(
                self.minimum_duration_seconds,
                int(
                    os.getenv(
                        "GEOCOOLING_COMMISSIONING_DEFAULT_TEST_SECONDS",
                        "5",
                    )
                ),
            ),
        )

        self.valve_preopen_seconds = max(
            0.0,
            min(
                30.0,
                float(
                    os.getenv(
                        "GEOCOOLING_COMMISSIONING_VALVE_PREOPEN_SECONDS",
                        str(
                            getattr(
                                controller,
                                "valve_open_delay",
                                5.0,
                            )
                        ),
                    )
                ),
            ),
        )

        self.valve_close_delay_seconds = max(
            0.0,
            min(
                30.0,
                float(
                    os.getenv(
                        "GEOCOOLING_COMMISSIONING_VALVE_CLOSE_DELAY_SECONDS",
                        str(
                            getattr(
                                controller,
                                "valve_close_delay",
                                2.0,
                            )
                        ),
                    )
                ),
            ),
        )

        self._lock = threading.RLock()
        self._cancel_event = threading.Event()
        self._worker: threading.Thread | None = None

        self.active_test: dict[str, Any] | None = None
        self.last_test: dict[str, Any] | None = None

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    def _controller_status(
        self,
    ) -> dict[str, Any]:
        result = self.controller.status()

        if not isinstance(result, dict):
            raise RuntimeError(
                "État du contrôleur invalide."
            )

        return result

    def _driver_status(
        self,
    ) -> dict[str, Any]:
        driver = getattr(
            self.controller,
            "driver",
            None,
        )

        if driver is None:
            return {}

        status_method = getattr(
            driver,
            "status",
            None,
        )

        if not callable(status_method):
            return {}

        result = status_method()

        if isinstance(result, dict):
            return result

        return {}

    def _simulation(
        self,
        controller_status: dict[str, Any],
    ) -> bool:
        driver_name = str(
            controller_status.get(
                "driver_name",
                getattr(
                    self.controller,
                    "driver_name",
                    "unknown",
                ),
            )
        ).lower()

        return bool(
            controller_status.get(
                "simulation",
                driver_name == "simulation",
            )
        )

    @staticmethod
    def _manual_command_active(
        controller_status: dict[str, Any],
    ) -> bool:
        manual = (
            controller_status.get(
                "manual_commands"
            )
            or controller_status.get(
                "manual_command"
            )
            or controller_status.get("manual")
            or {}
        )

        if not isinstance(manual, dict):
            return False

        active_value = manual.get("active")

        if isinstance(active_value, bool):
            if active_value:
                return True

        elif active_value:
            return True

        return bool(
            manual.get("active_command")
        )

    def _autopilot_enabled(self) -> bool:
        method = getattr(
            self.controller,
            "autopilot_status",
            None,
        )

        if callable(method):
            try:
                status = method()

                if isinstance(status, dict):
                    return bool(
                        status.get("enabled", False)
                    )
            except Exception:
                return True

        return bool(
            getattr(
                self.controller,
                "autopilot_enabled",
                False,
            )
        )

    def _validate_driver_methods(
        self,
    ) -> None:
        driver = getattr(
            self.controller,
            "driver",
            None,
        )

        if driver is None:
            raise RuntimeError(
                "Driver GeoCooling indisponible."
            )

        required = (
            "open_valve",
            "close_valve",
            "start_pump",
            "stop_pump",
        )

        missing = [
            name
            for name in required
            if not callable(
                getattr(
                    driver,
                    name,
                    None,
                )
            )
        ]

        if missing:
            raise RuntimeError(
                "Méthodes Driver absentes : "
                + ", ".join(missing)
            )

    def _validate_request(
        self,
        *,
        target: str,
        duration_seconds: int,
        confirmation: str | None,
    ) -> dict[str, Any]:
        target = target.lower().strip()

        if target not in {
            "valve",
            "pump",
        }:
            raise ValueError(
                "Actionneur inconnu."
            )

        if (
            duration_seconds
            < self.minimum_duration_seconds
            or duration_seconds
            > self.maximum_duration_seconds
        ):
            raise ValueError(
                "La durée doit être comprise entre "
                f"{self.minimum_duration_seconds} et "
                f"{self.maximum_duration_seconds} secondes."
            )

        controller_status = (
            self._controller_status()
        )

        state = str(
            controller_status.get(
                "state",
                "UNKNOWN",
            )
        ).upper()

        if state != "OFF":
            raise RuntimeError(
                "Le contrôleur doit être strictement OFF. "
                f"État actuel : {state}."
            )

        if self._manual_command_active(
            controller_status
        ):
            raise RuntimeError(
                "Une commande manuelle est active "
                "ou en attente."
            )

        if self._autopilot_enabled():
            raise RuntimeError(
                "L'Autopilot doit être désactivé "
                "pendant les tests de mise en service."
            )

        simulation = self._simulation(
            controller_status
        )

        if not simulation:
            if not self.real_tests_enabled:
                raise RuntimeError(
                    "Les tests physiques sont verrouillés. "
                    "Configurer "
                    "GEOCOOLING_COMMISSIONING_TESTS_ENABLED=true "
                    "après le raccordement."
                )

            if confirmation != CONFIRMATION_TEXT:
                raise RuntimeError(
                    "Confirmation physique invalide. "
                    "Valeur attendue : "
                    f"{CONFIRMATION_TEXT}"
                )

            device = self._mapping(
                controller_status.get("device")
            )

            if not bool(
                device.get("ready", False)
            ):
                raise RuntimeError(
                    "Le matériel GeoCooling n'est pas prêt."
                )

        self._validate_driver_methods()

        return {
            "controller_status": controller_status,
            "simulation": simulation,
        }

    def _update_active(
        self,
        **values: Any,
    ) -> None:
        with self._lock:
            if self.active_test is not None:
                self.active_test.update(values)

    def _sleep_interruptible(
        self,
        duration_seconds: float,
    ) -> bool:
        if duration_seconds <= 0:
            return not self._cancel_event.is_set()

        deadline = time.monotonic() + duration_seconds

        while time.monotonic() < deadline:
            if self._cancel_event.wait(
                min(
                    0.1,
                    max(
                        0.0,
                        deadline - time.monotonic(),
                    ),
                )
            ):
                return False

        return not self._cancel_event.is_set()

    def _safe_outputs_off(
        self,
        *,
        close_valve: bool = True,
    ) -> list[str]:
        errors: list[str] = []

        driver = getattr(
            self.controller,
            "driver",
            None,
        )

        if driver is None:
            return [
                "Driver indisponible pendant le nettoyage."
            ]

        try:
            driver.stop_pump()
        except Exception as exc:
            errors.append(
                f"Arrêt pompe : {exc}"
            )

        if close_valve:
            try:
                driver.close_valve()
            except Exception as exc:
                errors.append(
                    f"Fermeture vanne : {exc}"
                )

        return errors

    def _run_valve_test(
        self,
        test_id: str,
        duration_seconds: int,
    ) -> None:
        driver = self.controller.driver
        cleanup_errors: list[str] = []

        try:
            self._update_active(
                phase="OPENING_VALVE",
                message="Ouverture de la vanne.",
            )

            driver.open_valve()

            self._update_active(
                phase="VALVE_OPEN",
                message=(
                    "Vanne commandée ouverte, "
                    "temporisation en cours."
                ),
            )

            if not self._sleep_interruptible(
                duration_seconds
            ):
                raise InterruptedError(
                    "Test annulé."
                )

            self._update_active(
                phase="CLOSING_VALVE",
                message="Fermeture de la vanne.",
            )

            driver.close_valve()

            if not self._sleep_interruptible(
                self.valve_close_delay_seconds
            ):
                raise InterruptedError(
                    "Test annulé pendant la fermeture."
                )

            result = "COMPLETED"
            message = (
                "Test de la vanne terminé avec arrêt automatique."
            )
            error = None

        except InterruptedError as exc:
            result = "CANCELLED"
            message = str(exc)
            error = None

        except Exception as exc:
            logger.exception(
                "Échec du test de la vanne"
            )

            result = "FAILED"
            message = "Échec du test de la vanne."
            error = str(exc)

        finally:
            cleanup_errors.extend(
                self._safe_outputs_off(
                    close_valve=True,
                )
            )

            self._finalize(
                test_id=test_id,
                result=result,
                message=message,
                error=error,
                cleanup_errors=cleanup_errors,
            )

    def _run_pump_test(
        self,
        test_id: str,
        duration_seconds: int,
    ) -> None:
        driver = self.controller.driver
        cleanup_errors: list[str] = []

        try:
            self._update_active(
                phase="OPENING_VALVE",
                message=(
                    "Ouverture préalable obligatoire "
                    "de la vanne."
                ),
            )

            driver.open_valve()

            self._update_active(
                phase="WAITING_VALVE",
                message=(
                    "Attente de l'ouverture hydraulique "
                    "avant le circulateur."
                ),
            )

            if not self._sleep_interruptible(
                self.valve_preopen_seconds
            ):
                raise InterruptedError(
                    "Test annulé avant le démarrage "
                    "du circulateur."
                )

            self._update_active(
                phase="STARTING_PUMP",
                message="Démarrage du circulateur.",
            )

            driver.start_pump()

            self._update_active(
                phase="PUMP_RUNNING",
                message=(
                    "Circulateur actif, temporisation "
                    "de sécurité en cours."
                ),
            )

            if not self._sleep_interruptible(
                duration_seconds
            ):
                raise InterruptedError(
                    "Test annulé."
                )

            self._update_active(
                phase="STOPPING_PUMP",
                message="Arrêt du circulateur.",
            )

            driver.stop_pump()

            self._update_active(
                phase="CLOSING_VALVE",
                message="Fermeture de la vanne.",
            )

            driver.close_valve()

            if not self._sleep_interruptible(
                self.valve_close_delay_seconds
            ):
                raise InterruptedError(
                    "Test annulé pendant la fermeture."
                )

            result = "COMPLETED"
            message = (
                "Test du circulateur terminé avec "
                "arrêt automatique."
            )
            error = None

        except InterruptedError as exc:
            result = "CANCELLED"
            message = str(exc)
            error = None

        except Exception as exc:
            logger.exception(
                "Échec du test du circulateur"
            )

            result = "FAILED"
            message = "Échec du test du circulateur."
            error = str(exc)

        finally:
            cleanup_errors.extend(
                self._safe_outputs_off(
                    close_valve=True,
                )
            )

            self._finalize(
                test_id=test_id,
                result=result,
                message=message,
                error=error,
                cleanup_errors=cleanup_errors,
            )

    def _finalize(
        self,
        *,
        test_id: str,
        result: str,
        message: str,
        error: str | None,
        cleanup_errors: list[str],
    ) -> None:
        finished_at = utc_now()

        with self._lock:
            active = (
                dict(self.active_test)
                if self.active_test is not None
                else {
                    "id": test_id,
                }
            )

            active.update(
                {
                    "active": False,
                    "phase": result,
                    "result": result,
                    "message": message,
                    "error": error,
                    "cleanup_errors": cleanup_errors,
                    "finished_at": finished_at.isoformat(),
                }
            )

            if cleanup_errors and result == "COMPLETED":
                active["result"] = "COMPLETED_WITH_WARNINGS"
                active["phase"] = "COMPLETED_WITH_WARNINGS"

            self.last_test = active
            self.active_test = None
            self._worker = None
            self._cancel_event.clear()

    def start_test(
        self,
        *,
        target: str,
        duration_seconds: int | None = None,
        confirmation: str | None = None,
        requested_by: str = "api",
    ) -> dict[str, Any]:
        duration = (
            self.default_duration_seconds
            if duration_seconds is None
            else int(duration_seconds)
        )

        with self._lock:
            if (
                self._worker is not None
                and self._worker.is_alive()
            ):
                raise RuntimeError(
                    "Un test de mise en service "
                    "est déjà en cours."
                )

            validation = self._validate_request(
                target=target,
                duration_seconds=duration,
                confirmation=confirmation,
            )

            test_id = str(uuid.uuid4())
            started_at = utc_now()

            self._cancel_event.clear()

            self.active_test = {
                "id": test_id,
                "active": True,
                "target": target.lower(),
                "duration_seconds": duration,
                "requested_by": requested_by,
                "simulation": validation["simulation"],
                "phase": "ACCEPTED",
                "result": None,
                "message": "Test accepté.",
                "error": None,
                "cleanup_errors": [],
                "started_at": started_at.isoformat(),
                "finished_at": None,
            }

            worker_target = (
                self._run_valve_test
                if target.lower() == "valve"
                else self._run_pump_test
            )

            self._worker = threading.Thread(
                target=worker_target,
                args=(
                    test_id,
                    duration,
                ),
                daemon=True,
                name=(
                    "geocooling-commissioning-"
                    f"{target.lower()}"
                ),
            )

            self._worker.start()

            return dict(self.active_test)

    def cancel_test(self) -> dict[str, Any]:
        with self._lock:
            if (
                self._worker is None
                or not self._worker.is_alive()
                or self.active_test is None
            ):
                cleanup_errors = (
                    self._safe_outputs_off(
                        close_valve=True,
                    )
                )

                return {
                    "accepted": False,
                    "message": (
                        "Aucun test actif. "
                        "Une commande d'arrêt de sécurité "
                        "a néanmoins été envoyée."
                    ),
                    "cleanup_errors": cleanup_errors,
                }

            self._cancel_event.set()

            return {
                "accepted": True,
                "message": (
                    "Annulation demandée. "
                    "La pompe et la vanne vont être "
                    "remises à l'arrêt."
                ),
                "test_id": self.active_test.get("id"),
            }

    def status(self) -> dict[str, Any]:
        try:
            controller_status = (
                self._controller_status()
            )
            controller_error = None
        except Exception as exc:
            controller_status = {}
            controller_error = str(exc)

        simulation = bool(
            controller_status.get(
                "simulation",
                str(
                    getattr(
                        self.controller,
                        "driver_name",
                        "",
                    )
                ).lower()
                == "simulation",
            )
        )

        driver_status = {}

        try:
            driver_status = self._driver_status()
        except Exception as exc:
            driver_status = {
                "error": str(exc),
            }

        with self._lock:
            active = (
                dict(self.active_test)
                if self.active_test
                else None
            )

            last = (
                dict(self.last_test)
                if self.last_test
                else None
            )

            worker_running = bool(
                self._worker
                and self._worker.is_alive()
            )

        return {
            "component": "geocooling",
            "view": "commissioning_tests",
            "generated_at": utc_now().isoformat(),
            "real_tests_enabled": (
                self.real_tests_enabled
            ),
            "simulation": simulation,
            "confirmation_required": (
                not simulation
            ),
            "confirmation_text": (
                CONFIRMATION_TEXT
                if not simulation
                else None
            ),
            "limits": {
                "minimum_duration_seconds": (
                    self.minimum_duration_seconds
                ),
                "maximum_duration_seconds": (
                    self.maximum_duration_seconds
                ),
                "default_duration_seconds": (
                    self.default_duration_seconds
                ),
                "valve_preopen_seconds": (
                    self.valve_preopen_seconds
                ),
                "valve_close_delay_seconds": (
                    self.valve_close_delay_seconds
                ),
            },
            "interlocks": {
                "controller_must_be_off": True,
                "manual_command_must_be_inactive": True,
                "autopilot_must_be_disabled": True,
                "only_one_test_at_a_time": True,
                "pump_requires_valve_open": True,
                "automatic_stop": True,
            },
            "worker_running": worker_running,
            "active_test": active,
            "last_test": last,
            "controller": {
                "state": controller_status.get("state"),
                "mode": controller_status.get("mode"),
                "driver_name": controller_status.get(
                    "driver_name"
                ),
                "error": controller_error,
            },
            "driver": driver_status,
        }
