import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from app.geocooling.device_manager import DeviceManager
from app.geocooling.models import GeoCoolingMode, GeoCoolingState
from app.geocooling.mqtt_driver import MQTTDriver
from app.geocooling.simulator import SimulationDriver
from app.geocooling.runtime import RuntimeGuards
from app.geocooling.safety import GeoCoolingSafetyManager, SafetyDecision

logger = logging.getLogger("sbc.geocooling")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class GeoCoolingController:
    """
    Machine d'états GeoCooling V1.

    Séquence de démarrage :
        OFF
        -> OPENING_VALVE
        -> WAITING_FLOW
        -> STARTING_PUMP
        -> RUNNING

    Séquence d'arrêt :
        RUNNING
        -> STOPPING_PUMP
        -> WAITING_DRAIN
        -> CLOSING_VALVE
        -> OFF
    """

    def __init__(self) -> None:
        database_url = os.environ["DATABASE_URL"]

        self.engine = create_engine(
            database_url,
            pool_pre_ping=True,
        )

        self.driver_name = os.getenv(
            "GEOCOOLING_DRIVER",
            "simulation",
        ).strip().lower()

        if self.driver_name == "mqtt":
            self.driver = MQTTDriver()
            self.mode = GeoCoolingMode.MANUAL
        elif self.driver_name == "simulation":
            self.driver = SimulationDriver()
            self.mode = GeoCoolingMode.SIMULATION
        else:
            raise RuntimeError(
                "GEOCOOLING_DRIVER doit être "
                "'simulation' ou 'mqtt'."
            )

        self.device_manager = DeviceManager(
            self.driver
        )

        self.valve_open_delay = max(
            0.0,
            float(os.getenv("GEOCOOLING_VALVE_OPEN_DELAY", "5")),
        )

        self.valve_close_delay = max(
            0.0,
            float(os.getenv("GEOCOOLING_VALVE_CLOSE_DELAY", "2")),
        )

        self.max_runtime_seconds = max(
            60,
            int(os.getenv("GEOCOOLING_MAX_RUNTIME_SECONDS", "7200")),
        )
        self.minimum_on_seconds = max(
            0,
            int(os.getenv("GEOCOOLING_MINIMUM_ON_SECONDS", "300")),
        )
        self.minimum_off_seconds = max(
            0,
            int(os.getenv("GEOCOOLING_MINIMUM_OFF_SECONDS", "300")),
        )
        self.watchdog_interval_seconds = max(
            1,
            int(os.getenv("GEOCOOLING_WATCHDOG_INTERVAL_SECONDS", "5")),
        )
        self.runtime_guards = RuntimeGuards(
            minimum_on_seconds=self.minimum_on_seconds,
            minimum_off_seconds=self.minimum_off_seconds,
        )
        self.safety_manager = GeoCoolingSafetyManager()
        self._thermal_snapshot: dict[str, float | None] = {
            "indoor_temperature_c": None,
            "indoor_humidity_percent": None,
            "surface_temperature_c": None,
        }
        self._last_safety_decision: SafetyDecision = self.safety_manager.evaluate(
            **self._thermal_snapshot
        )

        self._lock = threading.RLock()
        self._stop_request = threading.Event()
        self._worker: threading.Thread | None = None

        self.state = GeoCoolingState.OFF

        self.state_changed_at = utc_now()
        self.started_at: datetime | None = None
        self.stopped_at: datetime | None = utc_now()

        self.last_event = "controller_initialized"
        self.last_reason = "Contrôleur initialisé en simulation"
        self.last_error: str | None = None

        self.cycle_count = 0

        self.initialize_database()
        self._restore_safe_state()
        self._persist_snapshot(
            event_type="geocooling.controller_initialized",
            reason=self.last_reason,
        )

    def initialize_database(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS geocooling_state (
                id BIGSERIAL PRIMARY KEY,
                created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                state TEXT NOT NULL,
                mode TEXT NOT NULL,
                valve_open BOOLEAN NOT NULL,
                pump_running BOOLEAN NOT NULL,
                simulation BOOLEAN NOT NULL,
                runtime_seconds INTEGER NOT NULL DEFAULT 0,
                event_type TEXT NOT NULL,
                reason TEXT,
                details JSONB NOT NULL DEFAULT '{}'::jsonb
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_geocooling_state_created_at
            ON geocooling_state (created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_geocooling_state_state
            ON geocooling_state (state)
            """,
        ]

        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def _restore_safe_state(self) -> None:
        self.driver.force_safe_state()
        self.state = GeoCoolingState.OFF
        self.state_changed_at = utc_now()
        self.started_at = None
        self.stopped_at = utc_now()

    def _runtime_seconds(self) -> int:
        if self.started_at is None:
            return 0

        end = (
            utc_now()
            if self.state != GeoCoolingState.OFF
            else self.stopped_at or utc_now()
        )

        return max(
            0,
            int((end - self.started_at).total_seconds()),
        )

    def _persist_snapshot(
        self,
        event_type: str,
        reason: str | None = None,
        details: dict[str, Any] | None = None,
    ) -> None:
        driver_status = self.driver.status()

        payload = {
            "cycle_count": self.cycle_count,
            "state_changed_at": self.state_changed_at.isoformat(),
            "started_at": (
                self.started_at.isoformat()
                if self.started_at
                else None
            ),
            "stopped_at": (
                self.stopped_at.isoformat()
                if self.stopped_at
                else None
            ),
            "last_error": self.last_error,
            **(details or {}),
        }

        try:
            with self.engine.begin() as connection:
                connection.execute(
                    text(
                        """
                        INSERT INTO geocooling_state (
                            state,
                            mode,
                            valve_open,
                            pump_running,
                            simulation,
                            runtime_seconds,
                            event_type,
                            reason,
                            details
                        )
                        VALUES (
                            :state,
                            :mode,
                            :valve_open,
                            :pump_running,
                            :simulation,
                            :runtime_seconds,
                            :event_type,
                            :reason,
                            CAST(:details AS JSONB)
                        )
                        """
                    ),
                    {
                        "state": self.state.value,
                        "mode": self.mode.value,
                        "valve_open": driver_status["valve_open"],
                        "pump_running": driver_status["pump_running"],
                        "simulation": True,
                        "runtime_seconds": self._runtime_seconds(),
                        "event_type": event_type,
                        "reason": reason,
                        "details": json.dumps(payload),
                    },
                )

                connection.execute(
                    text(
                        """
                        INSERT INTO system_events (
                            event_type,
                            details
                        )
                        VALUES (
                            :event_type,
                            CAST(:details AS JSONB)
                        )
                        """
                    ),
                    {
                        "event_type": event_type,
                        "details": json.dumps(
                            {
                                "component": "geocooling",
                                "state": self.state.value,
                                "mode": self.mode.value,
                                "reason": reason,
                                **payload,
                            }
                        ),
                    },
                )

        except Exception:
            logger.exception(
                "Échec de persistance de l'état GeoCooling"
            )

    def _transition(
        self,
        new_state: GeoCoolingState,
        event_type: str,
        reason: str,
    ) -> None:
        with self._lock:
            previous_state = self.state
            self.state = new_state
            self.state_changed_at = utc_now()
            self.last_event = event_type
            self.last_reason = reason

            logger.info(
                "GeoCooling %s -> %s : %s",
                previous_state.value,
                new_state.value,
                reason,
            )

            self._persist_snapshot(
                event_type=event_type,
                reason=reason,
                details={
                    "previous_state": previous_state.value,
                    "new_state": new_state.value,
                },
            )

    def _interruptible_wait(self, seconds: float) -> bool:
        """
        Retourne True si une demande d'arrêt est reçue
        pendant la temporisation.
        """
        return self._stop_request.wait(timeout=seconds)

    def request_start(self) -> dict[str, Any]:
        with self._lock:
            device_status = self.device_manager.status()

            if not device_status["ready"]:
                return {
                    "accepted": False,
                    "message": (
                        "Démarrage refusé : "
                        + device_status["reason"]
                    ),
                    "device": device_status,
                    "status": self.status(),
                }

            timing = self.runtime_guards.can_start(stopped_at=self.stopped_at)
            if not timing.allowed:
                return {
                    "accepted": False,
                    "message": timing.reason,
                    "timing": timing.as_dict(),
                    "status": self.status(),
                }

            safety = self.evaluate_safety()
            if not safety.safe:
                return {
                    "accepted": False,
                    "message": "Démarrage refusé par la sécurité anti-condensation",
                    "safety": safety.as_dict(),
                    "status": self.status(),
                }

            if self.state == GeoCoolingState.RUNNING:
                return {
                    "accepted": False,
                    "message": "Le GeoCooling fonctionne déjà.",
                    "status": self.status(),
                }

            if self.state not in {
                GeoCoolingState.OFF,
                GeoCoolingState.FAULT,
            }:
                return {
                    "accepted": False,
                    "message": (
                        "Une transition GeoCooling est déjà en cours."
                    ),
                    "status": self.status(),
                }

            if self._worker and self._worker.is_alive():
                return {
                    "accepted": False,
                    "message": "Le contrôleur est déjà occupé.",
                    "status": self.status(),
                }

            self.last_error = None
            self._stop_request.clear()

            self._worker = threading.Thread(
                target=self._start_sequence,
                name="geocooling-start-sequence",
                daemon=True,
            )
            self._worker.start()

            return {
                "accepted": True,
                "message": "Démarrage GeoCooling demandé.",
                "status": self.status(),
            }

    def _start_sequence(self) -> None:
        try:
            self._transition(
                GeoCoolingState.OPENING_VALVE,
                "geocooling.valve_opening",
                "Commande d'ouverture de l'électrovanne",
            )

            self.driver.open_valve()

            self._transition(
                GeoCoolingState.WAITING_FLOW,
                "geocooling.waiting_flow",
                (
                    "Temporisation après ouverture "
                    "de l'électrovanne"
                ),
            )

            if self._interruptible_wait(self.valve_open_delay):
                self._safe_stop_sequence(
                    "Démarrage interrompu par une demande d'arrêt"
                )
                return

            self._transition(
                GeoCoolingState.STARTING_PUMP,
                "geocooling.pump_starting",
                "Commande de démarrage du circulateur",
            )

            self.driver.start_pump()

            with self._lock:
                self.started_at = utc_now()
                self.stopped_at = None
                self.cycle_count += 1

            self._transition(
                GeoCoolingState.RUNNING,
                "geocooling.running",
                "GeoCooling en fonctionnement",
            )

            while not self._stop_request.wait(timeout=self.watchdog_interval_seconds):
                if self._runtime_seconds() >= self.max_runtime_seconds:
                    self._safe_stop_sequence(
                        "Durée maximale de fonctionnement atteinte",
                        enforce_minimum_on=False,
                    )
                    return

                device_status = self.device_manager.status()
                if not device_status["ready"]:
                    self._safe_stop_sequence(
                        "Watchdog matériel : " + device_status["reason"],
                        enforce_minimum_on=False,
                    )
                    return

                safety = self.evaluate_safety()
                if not safety.safe:
                    self._safe_stop_sequence(
                        "Sécurité anti-condensation : " + safety.reason,
                        enforce_minimum_on=False,
                    )
                    return

            # Une demande d'arrêt a réveillé la boucle.
            # En arrêt d'urgence, les actionneurs ont déjà été coupés
            # immédiatement et l'état EMERGENCY_STOP doit être conservé.
            with self._lock:
                emergency_active = (
                    self.state
                    == GeoCoolingState.EMERGENCY_STOP
                )

            if emergency_active:
                return

            self._safe_stop_sequence(
                "Arrêt manuel demandé"
            )

        except Exception as exc:
            logger.exception(
                "Défaut pendant la séquence de démarrage GeoCooling"
            )
            self.last_error = str(exc)
            self.driver.force_safe_state()

            self._transition(
                GeoCoolingState.FAULT,
                "geocooling.fault",
                str(exc),
            )

    def request_stop(self) -> dict[str, Any]:
        with self._lock:
            if self.state == GeoCoolingState.OFF:
                self.driver.force_safe_state()

                return {
                    "accepted": False,
                    "message": "Le GeoCooling est déjà arrêté.",
                    "status": self.status(),
                }

            self._stop_request.set()

            if not self._worker or not self._worker.is_alive():
                self._worker = threading.Thread(
                    target=self._safe_stop_sequence,
                    args=("Arrêt manuel demandé",),
                    name="geocooling-stop-sequence",
                    daemon=True,
                )
                self._worker.start()

            return {
                "accepted": True,
                "message": "Arrêt GeoCooling demandé.",
                "status": self.status(),
            }

    def _safe_stop_sequence(
        self,
        reason: str,
        *,
        enforce_minimum_on: bool = True,
    ) -> None:
        try:
            if enforce_minimum_on:
                timing = self.runtime_guards.can_stop(started_at=self.started_at)
                if not timing.allowed:
                    if self._interruptible_wait(timing.remaining_seconds):
                        pass
            self._transition(
                GeoCoolingState.STOPPING_PUMP,
                "geocooling.pump_stopping",
                reason,
            )

            self.driver.stop_pump()

            self._transition(
                GeoCoolingState.WAITING_DRAIN,
                "geocooling.waiting_drain",
                (
                    "Temporisation avant fermeture "
                    "de l'électrovanne"
                ),
            )

            time.sleep(self.valve_close_delay)

            self._transition(
                GeoCoolingState.CLOSING_VALVE,
                "geocooling.valve_closing",
                "Commande de fermeture de l'électrovanne",
            )

            self.driver.close_valve()

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

            self.last_error = str(exc)
            self.driver.force_safe_state()

            self._transition(
                GeoCoolingState.FAULT,
                "geocooling.fault",
                str(exc),
            )

    def emergency_stop(self) -> dict[str, Any]:
        with self._lock:
            self._stop_request.set()
            self.driver.force_safe_state()
            self.stopped_at = utc_now()

            self._transition(
                GeoCoolingState.EMERGENCY_STOP,
                "geocooling.emergency_stop",
                "Arrêt d'urgence demandé",
            )

            return {
                "accepted": True,
                "message": "Arrêt d'urgence exécuté.",
                "status": self.status(),
            }

    def reset(self) -> dict[str, Any]:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return {
                    "accepted": False,
                    "message": (
                        "Impossible de réinitialiser pendant "
                        "une transition active."
                    ),
                    "status": self.status(),
                }

            self._stop_request.clear()
            self.last_error = None
            self.driver.force_safe_state()
            self.started_at = None
            self.stopped_at = utc_now()

            self._transition(
                GeoCoolingState.OFF,
                "geocooling.reset",
                "Contrôleur réinitialisé",
            )

            return {
                "accepted": True,
                "message": "Contrôleur réinitialisé.",
                "status": self.status(),
            }

    def update_thermal_snapshot(
        self,
        *,
        indoor_temperature_c: float | None,
        indoor_humidity_percent: float | None,
        surface_temperature_c: float | None,
    ) -> dict[str, Any]:
        with self._lock:
            self._thermal_snapshot = {
                "indoor_temperature_c": indoor_temperature_c,
                "indoor_humidity_percent": indoor_humidity_percent,
                "surface_temperature_c": surface_temperature_c,
            }
            decision = self.evaluate_safety()
            self._persist_snapshot(
                event_type="geocooling.thermal_snapshot_updated",
                reason=decision.reason,
                details={"safety": decision.as_dict(), "thermal": dict(self._thermal_snapshot)},
            )
            return self.safety_status()

    def evaluate_safety(self) -> SafetyDecision:
        self._last_safety_decision = self.safety_manager.evaluate(**self._thermal_snapshot)
        return self._last_safety_decision

    def safety_status(self) -> dict[str, Any]:
        decision = self.evaluate_safety()
        return {
            "thermal": dict(self._thermal_snapshot),
            "decision": decision.as_dict(),
            "minimum_margin_c": self.safety_manager.minimum_margin_c,
            "require_thermal_sensors": self.safety_manager.require_thermal_sensors,
        }

    def diagnostics(self) -> dict[str, Any]:
        start_timing = self.runtime_guards.can_start(stopped_at=self.stopped_at)
        stop_timing = self.runtime_guards.can_stop(started_at=self.started_at)
        return {
            "status": self.status(),
            "safety": self.safety_status(),
            "timing": {
                "start": start_timing.as_dict(),
                "stop": stop_timing.as_dict(),
            },
            "worker_alive": bool(self._worker and self._worker.is_alive()),
        }

    def status(self) -> dict[str, Any]:
        with self._lock:
            driver_status = self.driver.status()

            return {
                "component": "geocooling",
                "state": self.state.value,
                "mode": self.mode.value,
                "simulation": bool(
                    driver_status.get(
                        "simulation",
                        False,
                    )
                ),
                "driver_name": self.driver_name,
                "device": self.device_manager.status(),
                "valve_open": driver_status["valve_open"],
                "pump_running": driver_status["pump_running"],
                "runtime_seconds": self._runtime_seconds(),
                "cycle_count": self.cycle_count,
                "state_changed_at": (
                    self.state_changed_at.isoformat()
                ),
                "started_at": (
                    self.started_at.isoformat()
                    if self.started_at
                    else None
                ),
                "stopped_at": (
                    self.stopped_at.isoformat()
                    if self.stopped_at
                    else None
                ),
                "last_event": self.last_event,
                "last_reason": self.last_reason,
                "last_error": self.last_error,
                "configuration": {
                    "valve_open_delay_seconds":
                        self.valve_open_delay,
                    "valve_close_delay_seconds":
                        self.valve_close_delay,
                    "max_runtime_seconds": self.max_runtime_seconds,
                    "minimum_on_seconds": self.minimum_on_seconds,
                    "minimum_off_seconds": self.minimum_off_seconds,
                    "watchdog_interval_seconds": self.watchdog_interval_seconds,
                },
                "driver": driver_status,
            }

    def history(self, limit: int = 50) -> list[dict[str, Any]]:
        safe_limit = min(max(limit, 1), 500)

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        created_at,
                        state,
                        mode,
                        valve_open,
                        pump_running,
                        simulation,
                        runtime_seconds,
                        event_type,
                        reason,
                        details
                    FROM geocooling_state
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": safe_limit},
            ).mappings().all()

        return [
            {
                **dict(row),
                "created_at": row["created_at"].isoformat(),
            }
            for row in rows
        ]
