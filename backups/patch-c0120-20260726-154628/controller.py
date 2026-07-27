import json
import logging
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import create_engine, text

from app.geocooling.brain import GeoCoolingBrain
from app.geocooling.brain_memory import BrainMemory
from app.geocooling.command_manager import CommandManager
from app.geocooling.device_manager import DeviceManager
from app.geocooling.models import (
    GeoCoolingMode,
    GeoCoolingState,
    ManualCommandStatus,
    ManualCommandType,
)
from app.geocooling.mqtt_driver import MQTTDriver
from app.geocooling.predictor import GeoCoolingPredictor
from app.geocooling.snapshot_builder import GeoCoolingSnapshotBuilder
from app.geocooling.simulator import SimulationDriver
from app.geocooling.safety import GeoCoolingSafetyManager
from app.geocooling.thermal import ThermalEngine

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
        self.safety_manager = GeoCoolingSafetyManager()
        self.thermal_engine = ThermalEngine()
        self.brain = GeoCoolingBrain()
        self.predictor = GeoCoolingPredictor()

        # PATCH C011A — Snapshot Builder
        self.snapshot_builder = GeoCoolingSnapshotBuilder(self)

        # PATCH C009A — Brain State Cache
        # Le cache est créé par api.py après le Controller, puis rattaché
        # explicitement. None conserve le comportement historique au démarrage.
        self.state_cache: Any | None = None

        # Gestion centralisée des futures commandes manuelles.
        # Ce composant ne pilote aucun relais directement.
        self.command_manager = CommandManager()

        # Historien PostgreSQL des décisions, commandes et événements.
        self.brain_memory = BrainMemory(self.engine)

        self.autopilot_enabled = (
            os.getenv(
                "GEOCOOLING_AUTOPILOT_ENABLED",
                "false",
            ).strip().lower()
            in {"1", "true", "yes", "on"}
        )

        self.autopilot_allow_real_driver = (
            os.getenv(
                "GEOCOOLING_AUTOPILOT_ALLOW_REAL_DRIVER",
                "false",
            ).strip().lower()
            in {"1", "true", "yes", "on"}
        )

        self.autopilot_interval_seconds = max(
            10,
            int(
                os.getenv(
                    "GEOCOOLING_AUTOPILOT_INTERVAL_SECONDS",
                    "30",
                )
            ),
        )

        self.autopilot_last_run_at: datetime | None = None
        self.autopilot_last_decision: str | None = None
        self.autopilot_last_action: str | None = None
        self.autopilot_last_reason: str | None = None
        self.autopilot_last_error: str | None = None

        # PATCH C009B — Brain telemetry
        self.brain_state_cache_decision_count = 0
        self.brain_live_fallback_decision_count = 0
        self.brain_last_input_source: str | None = None
        self.brain_last_snapshot_age_seconds: float | None = None
        self.brain_last_snapshot_stale: bool | None = None
        self.brain_last_telemetry_at: datetime | None = None
        self.brain_last_telemetry_error: str | None = None

        self._autopilot_stop_event = threading.Event()
        self._autopilot_worker: threading.Thread | None = None

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
            int(os.getenv("GEOCOOLING_MIN_ON_SECONDS", "180")),
        )
        self.minimum_off_seconds = max(
            0,
            int(os.getenv("GEOCOOLING_MIN_OFF_SECONDS", "300")),
        )
        self.watchdog_interval_seconds = max(
            1,
            int(os.getenv("GEOCOOLING_WATCHDOG_INTERVAL_SECONDS", "5")),
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
        self.brain_memory.initialize()
        self._restore_safe_state()
        self._persist_snapshot(
            event_type="geocooling.controller_initialized",
            reason=self.last_reason,
        )

        try:
            self.brain_memory.record_event(
                level="INFO",
                event_type="geocooling.controller_initialized",
                reason=self.last_reason,
                source="controller",
                details={
                    "driver_name": self.driver_name,
                    "mode": self.mode.value,
                    "state": self.state.value,
                    "autopilot_enabled": self.autopilot_enabled,
                },
            )
        except Exception:
            logger.exception(
                "Échec d'historisation du démarrage dans BrainMemory"
            )

        self._start_autopilot_worker()

    def _autopilot_allowed(self) -> tuple[bool, str]:
        if not self.autopilot_enabled:
            return False, "Autopilot désactivé"

        if (
            self.driver_name != "simulation"
            and not self.autopilot_allow_real_driver
        ):
            return (
                False,
                "Autopilot interdit sur le pilote réel",
            )

        return True, "Autopilot autorisé"

    def _brain_cache_telemetry(
        self,
    ) -> dict[str, Any]:
        """Expose l'état du cache utilisé pour les décisions du Brain."""

        telemetry: dict[str, Any] = {
            "attached": self.state_cache is not None,
            "ready": False,
            "running": False,
            "stale": None,
            "age_seconds": None,
            "captured_at": None,
            "capture_count": None,
            "error_count": None,
            "last_error": None,
        }

        cache = self.state_cache

        if cache is None:
            return telemetry

        telemetry["running"] = bool(
            getattr(cache, "running", False)
        )

        try:
            snapshot = cache.latest()

            if not isinstance(snapshot, dict):
                return telemetry

            telemetry.update(
                {
                    "ready": True,
                    "stale": bool(
                        snapshot.get("stale", True)
                    ),
                    "age_seconds": snapshot.get(
                        "age_seconds"
                    ),
                    "captured_at": snapshot.get(
                        "captured_at"
                    ),
                    "capture_count": snapshot.get(
                        "capture_count"
                    ),
                    "error_count": snapshot.get(
                        "error_count"
                    ),
                    "last_error": snapshot.get(
                        "last_error"
                    ),
                }
            )

        except Exception as exc:
            telemetry["last_error"] = str(exc)

        return telemetry

    def _record_brain_input_telemetry(
        self,
        brain: dict[str, Any],
    ) -> None:
        """Comptabilise la source réellement utilisée par le Brain."""

        source = str(
            brain.get("input_source") or "unknown"
        )

        self.brain_last_input_source = source
        self.brain_last_telemetry_at = utc_now()
        self.brain_last_telemetry_error = None

        if source == "state_cache":
            self.brain_state_cache_decision_count += 1
        else:
            self.brain_live_fallback_decision_count += 1

        try:
            telemetry = self._brain_cache_telemetry()

            age = telemetry.get("age_seconds")

            self.brain_last_snapshot_age_seconds = (
                float(age)
                if age is not None
                else None
            )

            stale = telemetry.get("stale")

            self.brain_last_snapshot_stale = (
                bool(stale)
                if stale is not None
                else None
            )

            error = telemetry.get("last_error")

            if error:
                self.brain_last_telemetry_error = str(
                    error
                )

        except Exception as exc:
            self.brain_last_telemetry_error = str(exc)

    def autopilot_status(self) -> dict[str, Any]:
        allowed, reason = self._autopilot_allowed()

        return {
            "enabled": self.autopilot_enabled,
            "allowed": allowed,
            "reason": reason,
            "simulation_only": (
                not self.autopilot_allow_real_driver
            ),
            "driver_name": self.driver_name,
            "interval_seconds": (
                self.autopilot_interval_seconds
            ),
            "worker_running": (
                self._autopilot_worker is not None
                and self._autopilot_worker.is_alive()
            ),
            "last_run_at": (
                self.autopilot_last_run_at.isoformat()
                if self.autopilot_last_run_at
                else None
            ),
            "last_decision": self.autopilot_last_decision,
            "last_action": self.autopilot_last_action,
            "last_reason": self.autopilot_last_reason,
            "last_error": self.autopilot_last_error,
            "brain_input": {
                "last_source":
                    self.brain_last_input_source,
                "state_cache_decision_count":
                    self.brain_state_cache_decision_count,
                "live_fallback_decision_count":
                    self.brain_live_fallback_decision_count,
                "last_snapshot_age_seconds":
                    self.brain_last_snapshot_age_seconds,
                "last_snapshot_stale":
                    self.brain_last_snapshot_stale,
                "last_telemetry_at": (
                    self.brain_last_telemetry_at.isoformat()
                    if self.brain_last_telemetry_at
                    else None
                ),
                "last_telemetry_error":
                    self.brain_last_telemetry_error,
                "cache": self._brain_cache_telemetry(),
            },
        }

    def _run_autopilot_cycle(self) -> None:
        self.autopilot_last_run_at = utc_now()
        self.autopilot_last_action = "NONE"
        self.autopilot_last_error = None

        allowed, reason = self._autopilot_allowed()

        if not allowed:
            self.autopilot_last_reason = reason
            return

        brain = self.brain_status()
        self._record_brain_input_telemetry(brain)

        decision = str(
            brain.get("decision", "WAIT")
        ).upper()

        self.autopilot_last_decision = decision

        reasons = brain.get("reason", [])
        if isinstance(reasons, list):
            decision_reason = "; ".join(
                str(item) for item in reasons
            )
        else:
            decision_reason = str(reasons)

        if decision == "START":
            if self.state == GeoCoolingState.OFF:
                result = self.request_start()

                if result.get("accepted"):
                    self.autopilot_last_action = "START"
                else:
                    self.autopilot_last_action = (
                        "START_REJECTED"
                    )

                self.autopilot_last_reason = str(
                    result.get(
                        "reason",
                        result.get(
                            "message",
                            decision_reason,
                        ),
                    )
                )
            else:
                self.autopilot_last_reason = (
                    "Démarrage inutile : contrôleur "
                    f"déjà dans l'état {self.state.value}"
                )

        elif decision == "STOP":
            if self.state != GeoCoolingState.OFF:
                result = self.request_stop()

                if result.get("accepted"):
                    self.autopilot_last_action = "STOP"
                else:
                    self.autopilot_last_action = (
                        "STOP_REJECTED"
                    )

                self.autopilot_last_reason = str(
                    result.get(
                        "reason",
                        result.get(
                            "message",
                            decision_reason,
                        ),
                    )
                )
            else:
                self.autopilot_last_reason = (
                    "Arrêt inutile : contrôleur déjà OFF"
                )

        else:
            self.autopilot_last_reason = (
                decision_reason
                or "Aucune action demandée par le Brain"
            )

    def _start_autopilot_worker(self) -> None:
        if (
            self._autopilot_worker is not None
            and self._autopilot_worker.is_alive()
        ):
            return

        def worker() -> None:
            while not self._autopilot_stop_event.is_set():
                try:
                    self._run_autopilot_cycle()
                except Exception as exc:
                    self.autopilot_last_error = str(exc)
                    logger.exception(
                        "Erreur du worker Autopilot GeoCooling"
                    )

                self._autopilot_stop_event.wait(
                    self.autopilot_interval_seconds
                )

        self._autopilot_worker = threading.Thread(
            target=worker,
            daemon=True,
            name="geocooling-autopilot",
        )
        self._autopilot_worker.start()

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
        self.stopped_at = None

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
                        "simulation": bool(driver_status.get("simulation", False)),
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

    def _remaining_minimum_off_seconds(self) -> int:
        if self.stopped_at is None:
            return 0
        elapsed = int((utc_now() - self.stopped_at).total_seconds())
        return max(0, self.minimum_off_seconds - elapsed)

    def _remaining_minimum_on_seconds(self) -> int:
        if self.started_at is None:
            return 0
        elapsed = int((utc_now() - self.started_at).total_seconds())
        return max(0, self.minimum_on_seconds - elapsed)

    def _thermal_safety(self) -> dict[str, Any]:
        latest = self.thermal_engine.latest()
        driver_status = self.driver.status()
        decision = self.safety_manager.evaluate(
            indoor_temperature_c=(latest.indoor_temperature_c if latest else driver_status.get("indoor_temperature_c")),
            indoor_humidity_percent=(latest.indoor_humidity_percent if latest else driver_status.get("indoor_humidity_percent")),
            surface_temperature_c=(latest.surface_temperature_c if latest else driver_status.get("surface_temperature_c")),
        )
        return decision.as_dict()

    def ingest_thermal_snapshot(self, payload: dict[str, Any]) -> dict[str, Any]:
        metrics = self.thermal_engine.ingest(payload)
        return {
            "accepted": True,
            "message": "Mesure thermique enregistrée.",
            "thermal": metrics,
            "safety": self._thermal_safety(),
        }

    def thermal_status(self) -> dict[str, Any]:
        metrics = self.thermal_engine.metrics()
        metrics["safety"] = self._thermal_safety()
        return metrics

    def thermal_history(self, limit: int = 200) -> list[dict[str, Any]]:
        return self.thermal_engine.history(limit)

    def prediction_status(self) -> dict[str, Any]:
        """
        Calcule la prévision thermique depuis le State Cache.

        Le dernier snapshot partagé est utilisé lorsqu'il contient un
        état thermique exploitable. Un repli live est conservé au
        démarrage, si le cache est indisponible, périmé ou incomplet.

        PATCH C010 — Predictor State Cache
        """

        cached_state = self._brain_cached_controller_state()

        source = "live"
        snapshot_age_seconds: float | None = None
        snapshot_stale: bool | None = None
        snapshot_sequence: int | None = None
        snapshot_captured_at: str | None = None

        state_value = self.state.value
        thermal = self.thermal_engine.metrics()

        if cached_state is not None:
            cached_thermal = self._cached_mapping(
                cached_state.get("thermal")
            )
            cached_state_value = cached_state.get("state")

            cache_payload_complete = bool(
                cached_thermal
                and isinstance(cached_state_value, str)
            )

            if cache_payload_complete:
                thermal = cached_thermal
                state_value = cached_state_value
                source = "state_cache"

                cache = self.state_cache

                if cache is not None:
                    try:
                        snapshot = cache.latest()

                        if isinstance(snapshot, dict):
                            age = snapshot.get("age_seconds")

                            if age is not None:
                                snapshot_age_seconds = float(age)

                            stale = snapshot.get("stale")

                            if stale is not None:
                                snapshot_stale = bool(stale)

                            sequence = snapshot.get("sequence")

                            if sequence is not None:
                                snapshot_sequence = int(sequence)

                            captured_at = snapshot.get(
                                "captured_at"
                            )

                            if captured_at is not None:
                                snapshot_captured_at = str(
                                    captured_at
                                )

                    except (
                        TypeError,
                        ValueError,
                        AttributeError,
                    ):
                        snapshot_age_seconds = None
                        snapshot_stale = None
                        snapshot_sequence = None
                        snapshot_captured_at = None

        prediction = self.predictor.predict(
            state=state_value,
            thermal=thermal,
        ).as_dict()

        prediction["configuration"] = (
            self.predictor.configuration()
        )

        prediction["input_source"] = source
        prediction["state_cache_attached"] = (
            self.state_cache is not None
        )

        prediction["state_cache"] = {
            "age_seconds": snapshot_age_seconds,
            "stale": snapshot_stale,
            "sequence": snapshot_sequence,
            "captured_at": snapshot_captured_at,
        }

        return prediction

    def attach_state_cache(
        self,
        state_cache: Any,
    ) -> None:
        """Rattache le cache partagé sans modifier le constructeur historique."""

        if state_cache is None:
            raise ValueError(
                "Un State Cache valide est requis."
            )

        cache_controller = getattr(
            state_cache,
            "controller",
            None,
        )

        if cache_controller is not self:
            raise ValueError(
                "Le State Cache n'est pas rattaché à ce Controller."
            )

        current = self.state_cache

        if current is not None and current is not state_cache:
            raise RuntimeError(
                "Un autre State Cache est déjà rattaché au Controller."
            )

        self.state_cache = state_cache

    @staticmethod
    def _cached_mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    def _brain_cached_controller_state(
        self,
    ) -> dict[str, Any] | None:
        """Retourne le dernier état Controller valide conservé par le cache."""

        cache = self.state_cache

        if cache is None:
            return None

        try:
            snapshot = cache.latest()
        except Exception:
            logger.exception(
                "Lecture du State Cache impossible pour le Brain"
            )
            return None

        if not isinstance(snapshot, dict):
            return None

        if snapshot.get("stale", False):
            return None

        controller_state = snapshot.get("controller")

        if not isinstance(controller_state, dict):
            return None

        return controller_state

    def brain_status(self) -> dict[str, Any]:
        """Calcule la décision Brain depuis le cache, avec repli live."""

        cached_state = self._brain_cached_controller_state()

        source = "live"

        if cached_state is not None:
            cached_thermal = self._cached_mapping(
                cached_state.get("thermal")
            )
            cached_safety = self._cached_mapping(
                cached_state.get("safety")
            )
            cached_device = self._cached_mapping(
                cached_state.get("device")
            )
            cached_anti_short_cycle = self._cached_mapping(
                cached_state.get("anti_short_cycle")
            )
            cached_prediction = self._cached_mapping(
                cached_state.get("prediction")
            )

            cached_state_value = cached_state.get("state")

            cache_payload_complete = bool(
                cached_thermal
                and cached_safety
                and cached_device
                and isinstance(cached_state_value, str)
            )

            if cache_payload_complete:
                thermal = cached_thermal
                safety = cached_safety
                device = cached_device
                anti_short_cycle = cached_anti_short_cycle
                prediction = cached_prediction
                state_value = cached_state_value
                source = "state_cache"
            else:
                cached_state = None

        if cached_state is None:
            thermal = self.thermal_engine.metrics()
            safety = self._thermal_safety()
            device = self.device_manager.status()
            anti_short_cycle = {
                "remaining_minimum_off_seconds":
                    self._remaining_minimum_off_seconds(),
                "remaining_minimum_on_seconds":
                    self._remaining_minimum_on_seconds(),
            }
            prediction = self.prediction_status()
            state_value = self.state.value

        decision = self.brain.evaluate(
            state=state_value,
            thermal=thermal,
            safety=safety,
            device=device,
            anti_short_cycle=anti_short_cycle,
            prediction=prediction,
        ).as_dict()

        decision["configuration"] = self.brain.configuration()
        decision["input_source"] = source
        decision["state_cache_attached"] = (
            self.state_cache is not None
        )

        cache_telemetry = self._brain_cache_telemetry()

        decision["state_cache"] = {
            "ready": cache_telemetry["ready"],
            "running": cache_telemetry["running"],
            "stale": cache_telemetry["stale"],
            "age_seconds": cache_telemetry["age_seconds"],
            "captured_at": cache_telemetry["captured_at"],
        }

        return decision

    def home_assistant_status(self) -> dict[str, Any]:
        """Vue stable et consolidée destinée à Home Assistant."""
        status = self.status()
        thermal = status.get("thermal") or {}
        latest = thermal.get("latest") or {}
        safety = status.get("safety") or {}
        brain = status.get("brain") or {}
        prediction = status.get("prediction") or {}
        device = status.get("device") or {}

        return {
            "available": True,
            "state": status.get("state"),
            "mode": status.get("mode"),
            "driver_name": status.get("driver_name"),
            "simulation": status.get("simulation"),
            "valve_open": status.get("valve_open"),
            "pump_running": status.get("pump_running"),
            "runtime_seconds": status.get("runtime_seconds"),
            "cycle_count": status.get("cycle_count"),
            "last_event": status.get("last_event"),
            "last_reason": status.get("last_reason"),
            "last_error": status.get("last_error"),
            "device_ready": device.get("ready"),
            "safety_safe": safety.get("safe"),
            "safety_reason": safety.get("reason"),
            "dew_point_c": safety.get("dew_point_c"),
            "condensation_margin_c": safety.get("margin_c"),
            "indoor_temperature_c": latest.get("indoor_temperature_c"),
            "indoor_humidity_percent": latest.get("indoor_humidity_percent"),
            "outdoor_temperature_c": latest.get("outdoor_temperature_c"),
            "surface_temperature_c": latest.get("surface_temperature_c"),
            "floor_supply_temperature_c": latest.get("floor_supply_temperature_c"),
            "floor_return_temperature_c": latest.get("floor_return_temperature_c"),
            "source_inlet_temperature_c": latest.get("source_inlet_temperature_c"),
            "source_outlet_temperature_c": latest.get("source_outlet_temperature_c"),
            "flow_rate_l_min": latest.get("flow_rate_l_min"),
            "cooling_power_kw": thermal.get("cooling_power_kw"),
            "brain_decision": brain.get("decision"),
            "brain_confidence": brain.get("confidence"),
            "brain_total_score": brain.get("total_score"),
            "brain_comfort_score": brain.get("comfort_score"),
            "brain_cooling_score": brain.get("cooling_score"),
            "brain_risk_score": brain.get("risk_score"),
            "brain_reason": "; ".join(brain.get("reason") or []),
            "brain_data_quality": brain.get("data_quality"),
            "brain_operating_mode": brain.get("operating_mode"),
            "recommended_runtime_minutes": brain.get("recommended_runtime_minutes"),
            "predicted_temperature_1h_c": brain.get("predicted_temperature_1h_c"),
            "predicted_temperature_3h_c": brain.get("predicted_temperature_3h_c"),
            "predicted_temperature_6h_c": brain.get("predicted_temperature_6h_c"),
            "prediction_confidence": prediction.get("confidence"),
            "prediction_method": prediction.get("method"),
            "anti_short_cycle": status.get("anti_short_cycle"),
            "generated_at": utc_now().isoformat(),
        }


    # PATCH-001F-MANUAL-SAFE-EXECUTION
    def _manual_record_event(
        self,
        *,
        event_type: str,
        reason: str,
        command: Any,
        level: str = "INFO",
        extra: dict[str, Any] | None = None,
    ) -> None:
        details = {
            "command_id": command.id,
            "command": command.command.value,
            "status": command.status.value,
            "requested_by": command.requested_by,
            "duration_seconds": command.duration_seconds,
            "controller_mode": self.mode.value,
            "controller_state": self.state.value,
        }

        if extra:
            details.update(extra)

        try:
            self.brain_memory.record_event(
                level=level,
                event_type=event_type,
                reason=reason,
                source="manual-executor",
                details=details,
            )
        except Exception:
            logger.exception(
                "Échec d'historisation d'un événement manuel"
            )

    def _manual_persist_command(
        self,
        command: Any,
    ) -> None:
        try:
            self.brain_memory.save_manual_command(command)
        except Exception:
            logger.exception(
                "Échec de persistance de la commande manuelle %s",
                command.id,
            )
            raise

    def _manual_refuse(
        self,
        command: Any,
        reason: str,
        *,
        level: str = "WARNING",
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        result = self.command_manager.refuse_active(
            command_id=command.id,
            refusal_reason=reason,
        )

        self._manual_persist_command(command)

        self._manual_record_event(
            event_type="geocooling.manual.command_refused",
            reason=reason,
            command=command,
            level=level,
            extra=details,
        )

        return {
            "accepted": False,
            "execution_started": False,
            "message": reason,
            "command": command.to_dict(),
            "manager_result": result,
            "controller": {
                "mode": self.mode.value,
                "state": self.state.value,
            },
        }

    def _manual_accept(
        self,
        command: Any,
        execution_result: dict[str, Any],
    ) -> dict[str, Any]:
        result = self.command_manager.accept_active(
            command_id=command.id,
        )

        if not result.get("accepted"):
            return self._manual_refuse(
                command,
                str(
                    result.get(
                        "reason",
                        "Impossible d'accepter la commande",
                    )
                ),
            )

        command.metadata["execution_result"] = dict(
            execution_result
        )
        command.metadata["execution_started_at"] = (
            utc_now().isoformat()
        )

        self._manual_persist_command(command)

        self._manual_record_event(
            event_type="geocooling.manual.command_accepted",
            reason="Commande validée et transmise au contrôleur",
            command=command,
            extra={
                "execution_result": execution_result,
            },
        )

        return {
            "accepted": True,
            "execution_started": True,
            "message": (
                "Commande validée et transmise au contrôleur."
            ),
            "command": command.to_dict(),
            "execution_result": execution_result,
            "controller": {
                "mode": self.mode.value,
                "state": self.state.value,
            },
        }

    def _manual_finish(
        self,
        command: Any,
        reason: str,
    ) -> None:
        if command.terminal:
            return

        result = self.command_manager.finish_active(
            command_id=command.id,
            reason=reason,
        )

        if not result.get("accepted"):
            return

        self._manual_persist_command(command)

        self._manual_record_event(
            event_type="geocooling.manual.command_finished",
            reason=reason,
            command=command,
        )

    def _manual_fail(
        self,
        command: Any,
        reason: str,
    ) -> None:
        if command.terminal:
            return

        try:
            self.command_manager.refuse_active(
                command_id=command.id,
                refusal_reason=reason,
            )
        except Exception:
            logger.exception(
                "Impossible de refuser la commande manuelle %s",
                command.id,
            )
            return

        try:
            self._manual_persist_command(command)
        finally:
            self._manual_record_event(
                event_type="geocooling.manual.execution_failed",
                reason=reason,
                command=command,
                level="ERROR",
            )

    def _manual_start_validation(
        self,
        command: Any,
    ) -> tuple[bool, str, dict[str, Any]]:
        device = self.device_manager.status()
        safety = self._thermal_safety()
        remaining_off = self._remaining_minimum_off_seconds()

        details = {
            "device": device,
            "safety": safety,
            "remaining_minimum_off_seconds": remaining_off,
        }

        if self.mode == GeoCoolingMode.OFF:
            return (
                False,
                "Le mode OFF interdit tout démarrage.",
                details,
            )

        if self.state == GeoCoolingState.EMERGENCY_STOP:
            return (
                False,
                "Le contrôleur est en arrêt d'urgence.",
                details,
            )

        if self.state == GeoCoolingState.FAULT:
            return (
                False,
                "Le contrôleur est en défaut et doit être réinitialisé.",
                details,
            )

        if self.state == GeoCoolingState.RUNNING:
            return (
                False,
                "Le GeoCooling fonctionne déjà.",
                details,
            )

        if self.state != GeoCoolingState.OFF:
            return (
                False,
                "Une transition GeoCooling est déjà en cours.",
                details,
            )

        if remaining_off > 0:
            return (
                False,
                (
                    "Anti-court-cycle actif : "
                    f"{remaining_off} seconde(s) restantes."
                ),
                details,
            )

        if not bool(device.get("ready", False)):
            return (
                False,
                str(
                    device.get(
                        "reason",
                        "Matériel GeoCooling indisponible.",
                    )
                ),
                details,
            )

        if not bool(safety.get("safe", False)):
            return (
                False,
                str(
                    safety.get(
                        "reason",
                        "Sécurité thermique non satisfaite.",
                    )
                ),
                details,
            )

        return (
            True,
            "Chaîne de sécurité validée.",
            details,
        )

    def cancel_manual_command(
        self,
        *,
        requested_by: str,
        reason: str,
    ) -> dict[str, Any]:
        """
        Annule une commande manuelle sans abandonner un équipement actif.

        Pour un START déjà accepté, une demande d'arrêt sécurisé est
        obligatoirement transmise au contrôleur avant l'archivage de la
        commande. Si l'arrêt est temporairement refusé par la durée
        minimale de marche, la commande reste active et supervisée.
        """

        command = self.command_manager.active_command_object()

        if command is None:
            return {
                "accepted": False,
                "status_code": 404,
                "message": (
                    "Aucune commande manuelle active à annuler."
                ),
            }

        stop_result: dict[str, Any] | None = None

        if (
            command.command == ManualCommandType.START
            and command.status == ManualCommandStatus.ACCEPTED
            and self.state != GeoCoolingState.OFF
        ):
            stop_result = self.request_stop()

            if (
                not stop_result.get("accepted")
                and self.state != GeoCoolingState.OFF
            ):
                command.metadata[
                    "cancellation_requested_at"
                ] = utc_now().isoformat()
                command.metadata[
                    "cancellation_requested_by"
                ] = requested_by
                command.metadata[
                    "cancellation_reason"
                ] = reason
                command.metadata[
                    "cancellation_stop_result"
                ] = dict(stop_result)

                self._manual_persist_command(command)

                self._manual_record_event(
                    event_type=(
                        "geocooling.manual."
                        "cancellation_deferred"
                    ),
                    reason=(
                        "Annulation différée : l'arrêt sécurisé "
                        "n'est pas encore autorisé."
                    ),
                    command=command,
                    level="WARNING",
                    extra={
                        "requested_by": requested_by,
                        "requested_reason": reason,
                        "stop_result": stop_result,
                    },
                )

                return {
                    "accepted": False,
                    "status_code": 409,
                    "message": (
                        "L'annulation est différée car le contrôleur "
                        "ne peut pas encore arrêter l'installation "
                        "en sécurité."
                    ),
                    "command": command.to_dict(),
                    "stop_result": stop_result,
                    "controller": {
                        "mode": self.mode.value,
                        "state": self.state.value,
                    },
                }

        result = self.command_manager.cancel(
            requested_by=requested_by,
            reason=reason,
        )

        if not result.get("accepted"):
            return {
                "accepted": False,
                "status_code": 409,
                "message": result.get(
                    "reason",
                    "La commande n'a pas pu être annulée.",
                ),
                "command": command.to_dict(),
            }

        command.metadata["cancellation_processed_at"] = (
            utc_now().isoformat()
        )

        if stop_result is not None:
            command.metadata[
                "cancellation_stop_result"
            ] = dict(stop_result)

        self._manual_persist_command(command)

        self._manual_record_event(
            event_type="geocooling.manual.command_cancelled",
            reason=reason,
            command=command,
            extra={
                "cancelled_by": requested_by,
                "stop_result": stop_result,
            },
        )

        return {
            "accepted": True,
            "status_code": 200,
            "message": "Commande manuelle annulée.",
            "command": command.to_dict(),
            "stop_result": stop_result,
            "controller": {
                "mode": self.mode.value,
                "state": self.state.value,
            },
        }

    def execute_pending_manual_command(
        self,
    ) -> dict[str, Any]:
        """
        Valide et exécute la commande PENDING active.

        START :
        - contrôles de mode, état, matériel, thermique et anti-cycle ;
        - lancement de la séquence normale request_start() ;
        - maintien jusqu'à expiration de la durée demandée ;
        - arrêt automatique à expiration.

        STOP :
        - toujours prioritaire pour ramener l'installation à l'arrêt ;
        - exécution via request_stop().
        """

        command = self.command_manager.active_command_object()

        if command is None:
            return {
                "accepted": False,
                "execution_started": False,
                "message": "Aucune commande manuelle active.",
            }

        if command.status != ManualCommandStatus.PENDING:
            return {
                "accepted": False,
                "execution_started": False,
                "message": (
                    "La commande n'est plus en attente de validation."
                ),
                "command": command.to_dict(),
            }

        if command.command == ManualCommandType.START:
            allowed, reason, details = (
                self._manual_start_validation(command)
            )

            if not allowed:
                return self._manual_refuse(
                    command,
                    reason,
                    details=details,
                )

            execution_result = self.request_start()

            if not execution_result.get("accepted"):
                return self._manual_refuse(
                    command,
                    str(
                        execution_result.get(
                            "reason",
                            execution_result.get(
                                "message",
                                "Démarrage refusé par le contrôleur.",
                            ),
                        )
                    ),
                    details={
                        "execution_result": execution_result,
                    },
                )

        elif command.command == ManualCommandType.STOP:
            if self.state == GeoCoolingState.OFF:
                accepted = self._manual_accept(
                    command,
                    {
                        "accepted": True,
                        "message": (
                            "Le contrôleur est déjà à l'arrêt."
                        ),
                        "state": self.state.value,
                    },
                )

                self._manual_finish(
                    command,
                    "Commande STOP satisfaite : contrôleur déjà OFF.",
                )

                accepted["execution_started"] = False
                accepted["message"] = (
                    "Commande STOP satisfaite immédiatement : "
                    "contrôleur déjà OFF."
                )
                accepted["command"] = command.to_dict()

                return accepted

            execution_result = self.request_stop()

            if not execution_result.get("accepted"):
                return self._manual_refuse(
                    command,
                    str(
                        execution_result.get(
                            "reason",
                            execution_result.get(
                                "message",
                                "Arrêt refusé par le contrôleur.",
                            ),
                        )
                    ),
                    details={
                        "execution_result": execution_result,
                    },
                )

        else:
            return self._manual_refuse(
                command,
                (
                    "Type de commande non exécutable : "
                    f"{command.command.value}"
                ),
            )

        response = self._manual_accept(
            command,
            execution_result,
        )

        worker = threading.Thread(
            target=self._monitor_manual_command,
            args=(command.id,),
            daemon=True,
            name=f"geocooling-manual-{command.id[:8]}",
        )
        worker.start()

        return response

    def _monitor_manual_command(
        self,
        command_id: str,
    ) -> None:
        """
        Suit l’exécution physique d’une commande acceptée.
        """

        started_wait_at = utc_now()
        transition_timeout_seconds = max(
            60,
            int(
                self.valve_open_delay
                + self.valve_close_delay
                + 120
            ),
        )

        while True:
            time.sleep(1)

            command = self.command_manager.active_command_object()

            if command is None or command.id != command_id:
                return

            if command.terminal:
                return

            cancellation_requested_at = command.metadata.get(
                "cancellation_requested_at"
            )

            if (
                cancellation_requested_at
                and command.command == ManualCommandType.START
            ):
                if self.state == GeoCoolingState.OFF:
                    self.command_manager.cancel(
                        requested_by=str(
                            command.metadata.get(
                                "cancellation_requested_by",
                                "system",
                            )
                        ),
                        reason=str(
                            command.metadata.get(
                                "cancellation_reason",
                                "Annulation différée exécutée",
                            )
                        ),
                    )

                    self._manual_persist_command(command)

                    self._manual_record_event(
                        event_type=(
                            "geocooling.manual."
                            "deferred_cancellation_finished"
                        ),
                        reason=(
                            "Annulation différée terminée après "
                            "arrêt sécurisé."
                        ),
                        command=command,
                    )
                    return

                stop_result = self.request_stop()

                if stop_result.get("accepted"):
                    command.metadata[
                        "deferred_stop_requested_at"
                    ] = utc_now().isoformat()
                    command.metadata[
                        "deferred_stop_result"
                    ] = dict(stop_result)
                    self._manual_persist_command(command)

            if self.state in {
                GeoCoolingState.FAULT,
                GeoCoolingState.EMERGENCY_STOP,
            }:
                self._manual_fail(
                    command,
                    (
                        "Exécution interrompue par l'état "
                        f"{self.state.value}."
                    ),
                )
                return

            if command.command == ManualCommandType.STOP:
                if self.state == GeoCoolingState.OFF:
                    self._manual_finish(
                        command,
                        "Arrêt manuel sécurisé terminé.",
                    )
                    return

            elif command.command == ManualCommandType.START:
                if command.expired:
                    command.metadata["expired_while_running"] = True
                    command.metadata["automatic_stop_requested_at"] = (
                        utc_now().isoformat()
                    )

                    self._manual_persist_command(command)

                    stop_result = self.request_stop()

                    self._manual_record_event(
                        event_type=(
                            "geocooling.manual.duration_expired"
                        ),
                        reason=(
                            "Durée de marche manuelle atteinte ; "
                            "arrêt automatique demandé."
                        ),
                        command=command,
                        level="WARNING",
                        extra={
                            "stop_result": stop_result,
                        },
                    )

                    if (
                        self.state == GeoCoolingState.OFF
                        or stop_result.get("accepted")
                    ):
                        while (
                            self.state != GeoCoolingState.OFF
                            and self.state
                            not in {
                                GeoCoolingState.FAULT,
                                GeoCoolingState.EMERGENCY_STOP,
                            }
                        ):
                            time.sleep(1)

                        if self.state == GeoCoolingState.OFF:
                            self._manual_finish(
                                command,
                                (
                                    "Durée manuelle atteinte et "
                                    "arrêt automatique terminé."
                                ),
                            )
                        else:
                            self._manual_fail(
                                command,
                                (
                                    "Défaut pendant l'arrêt "
                                    "automatique."
                                ),
                            )
                    else:
                        self._manual_fail(
                            command,
                            (
                                "Impossible de lancer l'arrêt "
                                "automatique."
                            ),
                        )

                    return

                if (
                    self.state != GeoCoolingState.RUNNING
                    and (
                        utc_now() - started_wait_at
                    ).total_seconds()
                    > transition_timeout_seconds
                ):
                    self._manual_fail(
                        command,
                        (
                            "Délai maximal de démarrage manuel "
                            "dépassé."
                        ),
                    )
                    return

    def request_start(self) -> dict[str, Any]:
        with self._lock:
            device_status = self.device_manager.status()
            thermal_safety = self._thermal_safety()
            remaining_off = self._remaining_minimum_off_seconds()

            if remaining_off > 0:
                return {
                    "accepted": False,
                    "message": (
                        "Démarrage refusé par l’anti-court-cycle : "
                        f"attendre encore {remaining_off} seconde(s)."
                    ),
                    "remaining_minimum_off_seconds": remaining_off,
                    "status": self.status(),
                }

            if not thermal_safety["safe"]:
                return {
                    "accepted": False,
                    "message": "Démarrage refusé par la sécurité thermique.",
                    "safety": thermal_safety,
                    "status": self.status(),
                }

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
                device_status = self.device_manager.status()
                if not device_status["ready"]:
                    self.last_error = device_status["reason"]
                    self.driver.force_safe_state()
                    self.stopped_at = utc_now()
                    self._transition(
                        GeoCoolingState.FAULT,
                        "geocooling.watchdog_fault",
                        "Watchdog matériel : " + device_status["reason"],
                    )
                    return

                thermal_safety = self._thermal_safety()
                if not thermal_safety["safe"]:
                    self.last_error = thermal_safety["reason"]
                    self._safe_stop_sequence(
                        "Arrêt de sécurité anti-condensation"
                    )
                    return

                if (
                    self._runtime_seconds()
                    >= self.max_runtime_seconds
                ):
                    self._safe_stop_sequence(
                        "Durée maximale de fonctionnement atteinte"
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

            remaining_on = self._remaining_minimum_on_seconds()
            if self.state == GeoCoolingState.RUNNING and remaining_on > 0:
                return {
                    "accepted": False,
                    "message": (
                        "Arrêt différé : durée minimale de marche non atteinte "
                        f"({remaining_on} seconde(s) restantes)."
                    ),
                    "remaining_minimum_on_seconds": remaining_on,
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

    def _safe_stop_sequence(self, reason: str) -> None:
        try:
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

    def _build_status_snapshot(self) -> dict[str, Any]:
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
                    "max_runtime_seconds":
                        self.max_runtime_seconds,
                    "minimum_on_seconds": self.minimum_on_seconds,
                    "minimum_off_seconds": self.minimum_off_seconds,
                    "watchdog_interval_seconds": self.watchdog_interval_seconds,
                    "minimum_dew_point_margin_c": self.safety_manager.minimum_margin_c,
                    "require_thermal_sensors": self.safety_manager.require_thermal_sensors,
                },
                "anti_short_cycle": {
                    "remaining_minimum_off_seconds": self._remaining_minimum_off_seconds(),
                    "remaining_minimum_on_seconds": self._remaining_minimum_on_seconds(),
                },
                "safety": self._thermal_safety(),
                "thermal": self.thermal_engine.metrics(),
                "brain": self.brain_status(),
                "prediction": self.prediction_status(),
                "manual_commands": self.command_manager.status(),
                "brain_memory": {
                    "enabled": True,
                    "tables": [
                        "brain_decisions",
                        "manual_commands",
                        "brain_events",
                    ],
                },
                "driver": driver_status,
            }

    def status(self) -> dict[str, Any]:
        """Retourne le snapshot construit par le Snapshot Builder.

        PATCH C011A — Snapshot Builder
        """
        return self.snapshot_builder.build()

    def diagnostics(self) -> dict[str, Any]:
        status = self.status()
        return {
            "component": "geocooling",
            "healthy": (
                status["state"] not in {
                    GeoCoolingState.FAULT.value,
                    GeoCoolingState.EMERGENCY_STOP.value,
                }
                and status["device"]["ready"]
                and status["safety"]["safe"]
            ),
            "state": status["state"],
            "device": status["device"],
            "safety": status["safety"],
            "thermal": status["thermal"],
            "brain": status["brain"],
            "prediction": status["prediction"],
            "manual_commands": status["manual_commands"],
            "brain_memory": status["brain_memory"],
            "anti_short_cycle": status["anti_short_cycle"],
            "configuration": status["configuration"],
            "last_error": status["last_error"],
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
