"""Flight Recorder en mémoire du sous-système GeoCooling.

Le Flight Recorder capture périodiquement l'état public du Controller.

Caractéristiques :

- lecture seule ;
- stockage circulaire en mémoire ;
- aucune écriture PostgreSQL ;
- aucune commande MQTT ;
- aucun pilotage de pompe ou de vanne ;
- aucune prise de décision ;
- aucune modification du Controller ou du Brain.
"""

from __future__ import annotations

import copy
import logging
import os
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any


logger = logging.getLogger(
    "sbc.geocooling.flight_recorder"
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    try:
        value = int(
            os.getenv(
                name,
                str(default),
            )
        )
    except (TypeError, ValueError):
        value = default

    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def env_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(
            os.getenv(
                name,
                str(default),
            )
        )
    except (TypeError, ValueError):
        value = default

    return max(
        minimum,
        min(
            maximum,
            value,
        ),
    )


def json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        ).isoformat()

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
            deque,
        ),
    ):
        return [
            json_safe(item)
            for item in value
        ]

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if enum_value is not None and not callable(
        enum_value
    ):
        return json_safe(enum_value)

    isoformat_method = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(isoformat_method):
        try:
            return isoformat_method()
        except Exception:
            pass

    return str(value)


class GeoCoolingFlightRecorder:
    """Enregistre périodiquement l'état du Controller en mémoire."""

    def __init__(
        self,
        controller: Any,
        state_cache: Any | None = None,
    ) -> None:
        self.controller = controller
        self.state_cache = state_cache

        self.capacity = env_int(
            "GEOCOOLING_FLIGHT_RECORDER_CAPACITY",
            default=300,
            minimum=10,
            maximum=3600,
        )

        self.interval_seconds = env_float(
            "GEOCOOLING_FLIGHT_RECORDER_INTERVAL_SECONDS",
            default=1.0,
            minimum=0.2,
            maximum=60.0,
        )

        self._snapshots: deque[
            dict[str, Any]
        ] = deque(
            maxlen=self.capacity
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()

        self._worker: threading.Thread | None = None

        self._started_at: datetime | None = None
        self._last_capture_at: datetime | None = None
        self._last_success_at: datetime | None = None
        self._last_error_at: datetime | None = None

        self._last_error: str | None = None

        self._capture_count = 0
        self._success_count = 0
        self._error_count = 0
        self._sequence = 0

        self.start()

    def _controller_status(
        self,
    ) -> dict[str, Any]:
        """Lit prioritairement le dernier état fourni par State Cache.

        Le Controller reste disponible comme repli de sécurité si le cache
        n'est pas fourni, pas encore prêt ou ne contient aucun état exploitable.
        """

        state_cache = self.state_cache

        if state_cache is not None:
            try:
                snapshot = state_cache.latest()

                if isinstance(snapshot, dict):
                    controller_state = snapshot.get(
                        "controller"
                    )

                    if isinstance(controller_state, dict):
                        return controller_state

            except Exception:
                # Le Flight Recorder ne doit pas être interrompu par une
                # indisponibilité temporaire du cache.
                pass

        return self.controller.status()

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    @staticmethod
    def _iso(
        value: datetime | None,
    ) -> str | None:
        if value is None:
            return None

        return value.isoformat()

    def _extract_summary(
        self,
        controller_status: dict[str, Any],
    ) -> dict[str, Any]:
        driver = self._mapping(
            controller_status.get("driver")
        )

        device = self._mapping(
            controller_status.get("device")
        )

        brain = self._mapping(
            controller_status.get("brain")
        )

        thermal = self._mapping(
            controller_status.get("thermal")
        )

        thermal_latest = self._mapping(
            thermal.get("latest")
        )

        safety = self._mapping(
            controller_status.get("safety")
        )

        manual = (
            controller_status.get(
                "manual_commands"
            )
            or controller_status.get(
                "manual_command"
            )
            or controller_status.get(
                "manual"
            )
            or {}
        )

        manual = self._mapping(manual)

        active_manual = (
            manual.get("active_command")
            or manual.get("active")
        )

        return {
            "state": controller_status.get(
                "state"
            ),
            "mode": controller_status.get(
                "mode"
            ),
            "simulation": controller_status.get(
                "simulation"
            ),
            "driver_name": controller_status.get(
                "driver_name",
                driver.get("driver"),
            ),
            "last_event": controller_status.get(
                "last_event"
            ),
            "last_reason": controller_status.get(
                "last_reason"
            ),
            "last_error": controller_status.get(
                "last_error"
            ),
            "pump_running": driver.get(
                "pump_running"
            ),
            "valve_open": driver.get(
                "valve_open"
            ),
            "driver_connected": driver.get(
                "connected"
            ),
            "device_online": device.get(
                "online",
                driver.get("device_online"),
            ),
            "device_ready": device.get(
                "ready"
            ),
            "heartbeat_fresh": device.get(
                "heartbeat_fresh"
            ),
            "brain_decision": brain.get(
                "decision"
            ),
            "brain_confidence": brain.get(
                "confidence"
            ),
            "brain_data_quality": brain.get(
                "data_quality"
            ),
            "indoor_temperature_c": (
                thermal_latest.get(
                    "indoor_temperature_c"
                )
            ),
            "indoor_humidity_percent": (
                thermal_latest.get(
                    "indoor_humidity_percent"
                )
            ),
            "surface_temperature_c": (
                thermal_latest.get(
                    "surface_temperature_c"
                )
            ),
            "floor_supply_temperature_c": (
                thermal_latest.get(
                    "floor_supply_temperature_c"
                )
            ),
            "floor_return_temperature_c": (
                thermal_latest.get(
                    "floor_return_temperature_c"
                )
            ),
            "source_inlet_temperature_c": (
                thermal_latest.get(
                    "source_inlet_temperature_c"
                )
            ),
            "source_outlet_temperature_c": (
                thermal_latest.get(
                    "source_outlet_temperature_c"
                )
            ),
            "outdoor_temperature_c": (
                thermal_latest.get(
                    "outdoor_temperature_c"
                )
            ),
            "flow_rate_l_min": (
                thermal_latest.get(
                    "flow_rate_l_min"
                )
            ),
            "thermal_timestamp": (
                thermal_latest.get(
                    "timestamp"
                )
            ),
            "safety_safe": safety.get(
                "safe"
            ),
            "safety_level": safety.get(
                "level"
            ),
            "dew_point_c": safety.get(
                "dew_point_c"
            ),
            "safety_margin_c": safety.get(
                "margin_c"
            ),
            "manual_command_active": bool(
                active_manual
            ),
        }

    def capture_once(
        self,
    ) -> dict[str, Any]:
        captured_at = utc_now()

        with self._lock:
            self._sequence += 1
            sequence = self._sequence

        try:
            raw_status = self._controller_status()

            if not isinstance(
                raw_status,
                dict,
            ):
                raise TypeError(
                    "controller.status() n'a pas retourné "
                    "un dictionnaire."
                )

            safe_status = json_safe(
                copy.deepcopy(raw_status)
            )

            snapshot = {
                "sequence": sequence,
                "captured_at": captured_at.isoformat(),
                "success": True,
                "error": None,
                "summary": self._extract_summary(
                    safe_status
                ),
                "controller": safe_status,
            }

            with self._lock:
                self._last_success_at = captured_at
                self._last_error = None
                self._success_count += 1

        except Exception as exc:
            logger.exception(
                "Échec de capture du Flight Recorder"
            )

            snapshot = {
                "sequence": sequence,
                "captured_at": captured_at.isoformat(),
                "success": False,
                "error": str(exc),
                "summary": {},
                "controller": {},
            }

            with self._lock:
                self._last_error_at = captured_at
                self._last_error = str(exc)
                self._error_count += 1

        with self._lock:
            self._snapshots.append(snapshot)
            self._capture_count += 1
            self._last_capture_at = captured_at

        return copy.deepcopy(snapshot)

    def _run(self) -> None:
        next_capture = time.monotonic()

        while not self._stop_event.is_set():
            now = time.monotonic()

            if now < next_capture:
                self._stop_event.wait(
                    next_capture - now
                )

                if self._stop_event.is_set():
                    break

            self.capture_once()

            next_capture += self.interval_seconds

            current = time.monotonic()

            if next_capture < current:
                next_capture = (
                    current
                    + self.interval_seconds
                )

    def start(self) -> bool:
        with self._lock:
            if (
                self._worker is not None
                and self._worker.is_alive()
            ):
                return False

            self._stop_event.clear()
            self._started_at = utc_now()

            self._worker = threading.Thread(
                target=self._run,
                daemon=True,
                name="geocooling-flight-recorder",
            )

            self._worker.start()

            return True

    def stop(self) -> bool:
        with self._lock:
            if (
                self._worker is None
                or not self._worker.is_alive()
            ):
                return False

            self._stop_event.set()
            worker = self._worker

        worker.join(
            timeout=max(
                2.0,
                self.interval_seconds * 2.0,
            )
        )

        return True

    def is_running(self) -> bool:
        with self._lock:
            return bool(
                self._worker
                and self._worker.is_alive()
            )

    def _select_snapshots(
        self,
        *,
        limit: int | None,
        errors_only: bool,
    ) -> list[dict[str, Any]]:
        with self._lock:
            snapshots = list(
                self._snapshots
            )

        if errors_only:
            snapshots = [
                item
                for item in snapshots
                if not item.get(
                    "success",
                    False,
                )
            ]

        if limit is not None:
            normalized_limit = max(
                1,
                min(
                    self.capacity,
                    int(limit),
                ),
            )

            snapshots = snapshots[
                -normalized_limit:
            ]

        return copy.deepcopy(snapshots)

    def latest(self) -> dict[str, Any]:
        with self._lock:
            snapshot = (
                copy.deepcopy(
                    self._snapshots[-1]
                )
                if self._snapshots
                else None
            )

        return {
            "component": "geocooling",
            "view": "flight_recorder_latest",
            "generated_at": utc_now().isoformat(),
            "read_only": True,
            "running": self.is_running(),
            "snapshot": snapshot,
        }

    def status(
        self,
        *,
        limit: int | None = None,
        errors_only: bool = False,
        include_controller: bool = True,
    ) -> dict[str, Any]:
        snapshots = self._select_snapshots(
            limit=limit,
            errors_only=errors_only,
        )

        if not include_controller:
            for snapshot in snapshots:
                snapshot.pop(
                    "controller",
                    None,
                )

        with self._lock:
            stored_count = len(
                self._snapshots
            )

            first_snapshot_at = (
                self._snapshots[0].get(
                    "captured_at"
                )
                if self._snapshots
                else None
            )

            last_snapshot_at = (
                self._snapshots[-1].get(
                    "captured_at"
                )
                if self._snapshots
                else None
            )

            worker_running = bool(
                self._worker
                and self._worker.is_alive()
            )

            metadata = {
                "capacity": self.capacity,
                "interval_seconds": (
                    self.interval_seconds
                ),
                "nominal_window_seconds": round(
                    self.capacity
                    * self.interval_seconds,
                    3,
                ),
                "stored_count": stored_count,
                "capture_count": (
                    self._capture_count
                ),
                "success_count": (
                    self._success_count
                ),
                "error_count": (
                    self._error_count
                ),
                "started_at": self._iso(
                    self._started_at
                ),
                "last_capture_at": self._iso(
                    self._last_capture_at
                ),
                "last_success_at": self._iso(
                    self._last_success_at
                ),
                "last_error_at": self._iso(
                    self._last_error_at
                ),
                "last_error": self._last_error,
                "first_snapshot_at": (
                    first_snapshot_at
                ),
                "last_snapshot_at": (
                    last_snapshot_at
                ),
            }

        return {
            "component": "geocooling",
            "view": "flight_recorder",
            "generated_at": utc_now().isoformat(),
            "read_only": True,
            "running": worker_running,
            "filters": {
                "limit": limit,
                "errors_only": errors_only,
                "include_controller": (
                    include_controller
                ),
            },
            "recorder": metadata,
            "returned_count": len(
                snapshots
            ),
            "snapshots": snapshots,
        }


    # PATCH C013.1R1 — Flight Recorder Event Consumer
    @staticmethod
    def _c0131_json_safe(value):
        """Convertit récursivement une valeur en structure JSON-safe."""

        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            return value

        if isinstance(value, dict):
            return {
                str(key): GeoCoolingFlightRecorder._c0131_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                GeoCoolingFlightRecorder._c0131_json_safe(item)
                for item in value
            ]

        isoformat = getattr(value, "isoformat", None)

        if callable(isoformat):
            try:
                return isoformat()
            except Exception:
                pass

        return repr(value)

    def record_bus_event(
        self,
        event_type,
        event,
    ):
        """Archive un événement provenant du GeoCoolingEventBus."""

        import threading
        from collections import deque
        from datetime import datetime, timezone

        if not hasattr(self, "_c0131_bus_event_lock"):
            self._c0131_bus_event_lock = threading.RLock()

        if not hasattr(self, "_c0131_bus_events"):
            self._c0131_bus_events = deque(maxlen=500)

        if not hasattr(self, "_c0131_bus_metrics"):
            self._c0131_bus_metrics = {
                "received_count": 0,
                "error_count": 0,
                "last_received_at": None,
                "last_event_type": None,
            }

        received_at = datetime.now(
            timezone.utc
        ).isoformat()

        entry = {
            "event_type": str(event_type),
            "event": self._c0131_json_safe(event),
            "received_at": received_at,
        }

        with self._c0131_bus_event_lock:
            self._c0131_bus_events.append(entry)

            self._c0131_bus_metrics[
                "received_count"
            ] += 1

            self._c0131_bus_metrics[
                "last_received_at"
            ] = received_at

            self._c0131_bus_metrics[
                "last_event_type"
            ] = str(event_type)

        return entry

    def bus_events_history(
        self,
        limit=100,
    ):
        """Retourne les derniers événements reçus du bus."""

        normalized_limit = max(
            0,
            min(int(limit), 500),
        )

        events = list(
            getattr(
                self,
                "_c0131_bus_events",
                (),
            )
        )

        if normalized_limit == 0:
            return []

        return events[-normalized_limit:]

    def bus_events_status(self):
        """Retourne l'état du consumer Event Bus."""

        events = getattr(
            self,
            "_c0131_bus_events",
            (),
        )

        metrics = dict(
            getattr(
                self,
                "_c0131_bus_metrics",
                {
                    "received_count": 0,
                    "error_count": 0,
                    "last_received_at": None,
                    "last_event_type": None,
                },
            )
        )

        return {
            "overall": "OK",
            "component": "flight_recorder_consumer",
            "patch_version": "C013.1R1",
            "running": True,
            "event_count": len(events),
            "capacity": 500,
            "metrics": metrics,
        }
