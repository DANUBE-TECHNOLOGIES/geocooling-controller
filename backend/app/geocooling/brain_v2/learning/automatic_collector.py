from __future__ import annotations

import hashlib
import json
import logging
import math
import os
import threading
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.geocooling.brain_v2.learning.thermal_learning_engine import (
    ThermalLearningEngine,
)


LOGGER = logging.getLogger(
    "sbc.geocooling.brain_v2.collector"
)


class AutomaticObservationCollector:
    VERSION = "C022.3-AUTO-COLLECTOR-1.0"

    DEFAULT_ENDPOINTS = (
        "/geocooling/thermal",
        "/geocooling/home-assistant/dashboard",
        "/geocooling/status",
    )

    FIELD_ALIASES = {
        "indoor_temperature_c": (
            "indoor_temperature_c",
            "indoor_temperature",
            "temperature_indoor_c",
            "inside_temperature",
            "room_temperature",
            "temperature_interieure",
        ),
        "indoor_humidity_percent": (
            "indoor_humidity_percent",
            "indoor_humidity",
            "humidity_indoor",
            "inside_humidity",
            "humidity_percent",
        ),
        "outdoor_temperature_c": (
            "outdoor_temperature_c",
            "outdoor_temperature",
            "temperature_outdoor_c",
            "outside_temperature",
            "temperature_exterieure",
        ),
        "floor_surface_temperature_c": (
            "floor_surface_temperature_c",
            "floor_surface_temperature",
            "surface_temperature_c",
            "floor_surface_c",
        ),
        "floor_supply_temperature_c": (
            "floor_supply_temperature_c",
            "floor_supply_temperature",
            "supply_temperature_c",
            "departure_temperature_c",
            "floor_departure_temperature_c",
        ),
        "floor_return_temperature_c": (
            "floor_return_temperature_c",
            "floor_return_temperature",
            "return_temperature_c",
        ),
        "source_inlet_temperature_c": (
            "source_inlet_temperature_c",
            "source_in_temperature_c",
            "source_temperature_in_c",
        ),
        "source_outlet_temperature_c": (
            "source_outlet_temperature_c",
            "source_out_temperature_c",
            "source_temperature_out_c",
        ),
        "flow_rate_l_min": (
            "flow_rate_l_min",
            "flow_l_min",
            "hydraulic_flow_l_min",
            "flow_rate",
        ),
        "pump_running": (
            "pump_running",
            "pump",
            "pump_active",
            "circulator_running",
        ),
        "valve_open": (
            "valve_open",
            "valve",
            "valve_active",
        ),
        "active_cooling": (
            "active_cooling",
            "cooling_active",
            "cooling",
        ),
        "brain_decision": (
            "brain_decision",
            "decision",
            "recommended_action",
        ),
        "brain_confidence_percent": (
            "brain_confidence_percent",
            "brain_confidence",
            "confidence_percent",
            "confidence",
        ),
    }

    NUMERIC_FIELDS = {
        "indoor_temperature_c",
        "indoor_humidity_percent",
        "outdoor_temperature_c",
        "floor_surface_temperature_c",
        "floor_supply_temperature_c",
        "floor_return_temperature_c",
        "source_inlet_temperature_c",
        "source_outlet_temperature_c",
        "flow_rate_l_min",
        "brain_confidence_percent",
    }

    BOOLEAN_FIELDS = {
        "pump_running",
        "valve_open",
        "active_cooling",
    }

    def __init__(
        self,
        data_directory: str | Path | None = None,
        base_url: str | None = None,
        collection_interval_seconds: int | None = None,
        training_interval_seconds: int | None = None,
        initial_delay_seconds: int | None = None,
    ) -> None:
        configured_directory = (
            data_directory
            or os.getenv(
                "GEOCOOLING_BRAIN_V2_DATA_DIR",
                "/app/data/geocooling/brain_v2",
            )
        )

        self.data_directory = Path(
            configured_directory
        )

        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.observations_path = (
            self.data_directory
            / "observations.jsonl"
        )

        self.state_path = (
            self.data_directory
            / "automatic-collector.json"
        )

        self.base_url = (
            base_url
            or os.getenv(
                "GEOCOOLING_INTERNAL_API_URL",
                "http://127.0.0.1:8000",
            )
        ).rstrip("/")

        self.collection_interval_seconds = max(
            int(
                collection_interval_seconds
                or os.getenv(
                    "GEOCOOLING_BRAIN_V2_COLLECTION_INTERVAL",
                    "300",
                )
            ),
            60,
        )

        self.training_interval_seconds = max(
            int(
                training_interval_seconds
                or os.getenv(
                    "GEOCOOLING_BRAIN_V2_TRAINING_INTERVAL",
                    "1800",
                )
            ),
            300,
        )

        self.initial_delay_seconds = max(
            int(
                initial_delay_seconds
                if initial_delay_seconds is not None
                else os.getenv(
                    "GEOCOOLING_BRAIN_V2_INITIAL_DELAY",
                    "20",
                )
            ),
            0,
        )

        self.enabled = (
            os.getenv(
                "GEOCOOLING_BRAIN_V2_AUTO_COLLECT",
                "true",
            ).strip().lower()
            not in {
                "0",
                "false",
                "no",
                "off",
            }
        )

        configured_endpoints = os.getenv(
            "GEOCOOLING_BRAIN_V2_SOURCE_ENDPOINTS",
            "",
        ).strip()

        if configured_endpoints:
            self.endpoints = tuple(
                item.strip()
                for item in configured_endpoints.split(",")
                if item.strip()
            )
        else:
            self.endpoints = self.DEFAULT_ENDPOINTS

        self.engine = ThermalLearningEngine(
            data_directory=self.data_directory
        )

        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None
        self._lock = threading.RLock()

        self._state = self._load_state()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _as_float(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, dict):
            for key in (
                "value",
                "state",
                "temperature",
                "reading",
            ):
                if key in value:
                    return AutomaticObservationCollector._as_float(
                        value[key]
                    )

            return None

        if isinstance(value, str):
            cleaned = (
                value.strip()
                .replace(",", ".")
                .replace("°C", "")
                .replace("%", "")
            )

            try:
                value = float(cleaned)
            except ValueError:
                return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(result):
            return None

        return result

    @staticmethod
    def _as_bool(
        value: Any,
    ) -> bool | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return value

        if isinstance(value, dict):
            for key in (
                "value",
                "state",
                "active",
                "running",
                "open",
            ):
                if key in value:
                    return AutomaticObservationCollector._as_bool(
                        value[key]
                    )

            return None

        if isinstance(value, (int, float)):
            return value != 0

        if isinstance(value, str):
            normalized = value.strip().lower()

            if normalized in {
                "1",
                "true",
                "yes",
                "on",
                "active",
                "running",
                "open",
                "cooling",
            }:
                return True

            if normalized in {
                "0",
                "false",
                "no",
                "off",
                "inactive",
                "stopped",
                "closed",
                "idle",
            }:
                return False

        return None

    @staticmethod
    def _flatten(
        value: Any,
        result: dict[str, Any],
    ) -> None:
        if isinstance(value, dict):
            for key, child in value.items():
                normalized_key = str(
                    key
                ).strip().lower()

                if normalized_key not in result:
                    result[normalized_key] = child

                AutomaticObservationCollector._flatten(
                    child,
                    result,
                )

        elif isinstance(value, list):
            for child in value:
                AutomaticObservationCollector._flatten(
                    child,
                    result,
                )

    @staticmethod
    def _extract_text(
        value: Any,
    ) -> str | None:
        if value is None:
            return None

        if isinstance(value, dict):
            for key in (
                "value",
                "state",
                "decision",
                "action",
            ):
                if key in value:
                    return AutomaticObservationCollector._extract_text(
                        value[key]
                    )

            return None

        text = str(value).strip()

        return text or None

    def _normalize_payload(
        self,
        payload: dict[str, Any],
        source_endpoint: str,
    ) -> dict[str, Any]:
        flattened: dict[str, Any] = {}

        self._flatten(
            payload,
            flattened,
        )

        observation: dict[str, Any] = {
            "timestamp": self._utc_now(),
            "source": (
                "c0223_automatic_collector"
            ),
            "metadata": {
                "collector_version": self.VERSION,
                "source_endpoint": source_endpoint,
                "automatic": True,
                "decision_authority": False,
                "hardware_control": False,
            },
        }

        for target_field, aliases in (
            self.FIELD_ALIASES.items()
        ):
            raw_value = None

            for alias in aliases:
                if alias in flattened:
                    raw_value = flattened[alias]
                    break

            if target_field in self.NUMERIC_FIELDS:
                converted = self._as_float(
                    raw_value
                )

            elif target_field in self.BOOLEAN_FIELDS:
                converted = self._as_bool(
                    raw_value
                )

            else:
                converted = self._extract_text(
                    raw_value
                )

            if converted is not None:
                observation[target_field] = converted

        if "active_cooling" not in observation:
            pump = observation.get(
                "pump_running"
            )

            valve = observation.get(
                "valve_open"
            )

            if pump is not None and valve is not None:
                observation["active_cooling"] = bool(
                    pump and valve
                )

        return observation

    def _fetch_endpoint(
        self,
        endpoint: str,
    ) -> dict[str, Any]:
        if endpoint.startswith(
            ("http://", "https://")
        ):
            url = endpoint
        else:
            url = (
                self.base_url
                + "/"
                + endpoint.lstrip("/")
            )

        request = Request(
            url=url,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": self.VERSION,
            },
        )

        with urlopen(
            request,
            timeout=5,
        ) as response:
            payload = json.loads(
                response.read().decode(
                    "utf-8"
                )
            )

        if not isinstance(payload, dict):
            raise ValueError(
                "La réponse API n’est pas un objet JSON"
            )

        return payload

    @staticmethod
    def _fingerprint(
        observation: dict[str, Any],
    ) -> str:
        ignored = {
            "timestamp",
            "metadata",
        }

        stable_payload = {
            key: value
            for key, value in observation.items()
            if key not in ignored
        }

        encoded = json.dumps(
            stable_payload,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")

        return hashlib.sha256(
            encoded
        ).hexdigest()

    @staticmethod
    def _usable_measurement_count(
        observation: dict[str, Any],
    ) -> int:
        important_fields = (
            "indoor_temperature_c",
            "outdoor_temperature_c",
            "floor_surface_temperature_c",
            "floor_supply_temperature_c",
            "floor_return_temperature_c",
            "source_inlet_temperature_c",
            "source_outlet_temperature_c",
            "flow_rate_l_min",
            "pump_running",
            "valve_open",
        )

        return sum(
            1
            for field in important_fields
            if field in observation
        )

    def _append_observation(
        self,
        observation: dict[str, Any],
    ) -> None:
        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        with self.observations_path.open(
            "a",
            encoding="utf-8",
        ) as handle:
            handle.write(
                json.dumps(
                    observation,
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )

            handle.write("\n")
            handle.flush()
            os.fsync(handle.fileno())

    def _default_state(
        self,
    ) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "enabled": self.enabled,
            "running": False,
            "collection_interval_seconds": (
                self.collection_interval_seconds
            ),
            "training_interval_seconds": (
                self.training_interval_seconds
            ),
            "collection_attempts": 0,
            "successful_collections": 0,
            "rejected_collections": 0,
            "duplicate_collections": 0,
            "training_attempts": 0,
            "successful_trainings": 0,
            "last_collection_at": None,
            "last_training_at": None,
            "last_source_endpoint": None,
            "last_observation_fingerprint": None,
            "last_error": None,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
        }

    def _load_state(
        self,
    ) -> dict[str, Any]:
        default = self._default_state()

        if not self.state_path.exists():
            return default

        try:
            loaded = json.loads(
                self.state_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return default

        if not isinstance(loaded, dict):
            return default

        default.update(loaded)

        default.update(
            {
                "version": self.VERSION,
                "enabled": self.enabled,
                "running": False,
                "collection_interval_seconds": (
                    self.collection_interval_seconds
                ),
                "training_interval_seconds": (
                    self.training_interval_seconds
                ),
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
            }
        )

        return default

    def _save_state(
        self,
    ) -> None:
        temporary_path = self.state_path.with_suffix(
            ".json.tmp"
        )

        temporary_path.write_text(
            json.dumps(
                self._state,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            self.state_path,
        )

    def collect_once(
        self,
        force: bool = False,
    ) -> dict[str, Any]:
        with self._lock:
            self._state["collection_attempts"] = (
                int(
                    self._state.get(
                        "collection_attempts",
                        0,
                    )
                )
                + 1
            )

            errors: list[str] = []

            for endpoint in self.endpoints:
                try:
                    raw_payload = self._fetch_endpoint(
                        endpoint
                    )

                    observation = self._normalize_payload(
                        raw_payload,
                        endpoint,
                    )

                    measurement_count = (
                        self._usable_measurement_count(
                            observation
                        )
                    )

                    if measurement_count < 1:
                        errors.append(
                            f"{endpoint}: aucune mesure exploitable"
                        )
                        continue

                    fingerprint = self._fingerprint(
                        observation
                    )

                    previous_fingerprint = (
                        self._state.get(
                            "last_observation_fingerprint"
                        )
                    )

                    if (
                        not force
                        and fingerprint
                        == previous_fingerprint
                    ):
                        self._state[
                            "duplicate_collections"
                        ] = (
                            int(
                                self._state.get(
                                    "duplicate_collections",
                                    0,
                                )
                            )
                            + 1
                        )

                        self._state["last_error"] = None
                        self._save_state()

                        return {
                            "result": "DUPLICATE_SKIPPED",
                            "source_endpoint": endpoint,
                            "measurement_count": (
                                measurement_count
                            ),
                            "fingerprint": fingerprint,
                            "observation": observation,
                        }

                    self._append_observation(
                        observation
                    )

                    self._state[
                        "successful_collections"
                    ] = (
                        int(
                            self._state.get(
                                "successful_collections",
                                0,
                            )
                        )
                        + 1
                    )

                    self._state[
                        "last_collection_at"
                    ] = observation["timestamp"]

                    self._state[
                        "last_source_endpoint"
                    ] = endpoint

                    self._state[
                        "last_observation_fingerprint"
                    ] = fingerprint

                    self._state["last_error"] = None

                    self._save_state()

                    return {
                        "result": "OBSERVATION_RECORDED",
                        "source_endpoint": endpoint,
                        "measurement_count": (
                            measurement_count
                        ),
                        "fingerprint": fingerprint,
                        "observation": observation,
                    }

                except (
                    HTTPError,
                    URLError,
                    TimeoutError,
                    ValueError,
                    OSError,
                    json.JSONDecodeError,
                ) as exc:
                    errors.append(
                        f"{endpoint}: {exc}"
                    )

            self._state[
                "rejected_collections"
            ] = (
                int(
                    self._state.get(
                        "rejected_collections",
                        0,
                    )
                )
                + 1
            )

            error_message = "; ".join(
                errors
            ) or "Aucune source disponible"

            self._state["last_error"] = (
                error_message
            )

            self._save_state()

            return {
                "result": "NO_SOURCE_AVAILABLE",
                "errors": errors,
            }

    def train_once(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            self._state["training_attempts"] = (
                int(
                    self._state.get(
                        "training_attempts",
                        0,
                    )
                )
                + 1
            )

            try:
                model = self.engine.train()

                self._state[
                    "successful_trainings"
                ] = (
                    int(
                        self._state.get(
                            "successful_trainings",
                            0,
                        )
                    )
                    + 1
                )

                self._state[
                    "last_training_at"
                ] = self._utc_now()

                self._state["last_error"] = None

                self._save_state()

                return {
                    "result": "TRAINING_COMPLETED",
                    "status": model.status,
                    "learning_state": (
                        model.learning_state
                    ),
                    "valid_observations": (
                        model.valid_observations
                    ),
                    "usable_transitions": (
                        model.usable_transitions
                    ),
                    "global_confidence_percent": (
                        model.global_confidence_percent
                    ),
                }

            except Exception as exc:
                self._state["last_error"] = (
                    f"Training failed: {exc}"
                )

                self._save_state()

                raise

    def cycle_once(
        self,
        force_collection: bool = False,
    ) -> dict[str, Any]:
        collection = self.collect_once(
            force=force_collection
        )

        training = self.train_once()

        return {
            "collector_version": self.VERSION,
            "collection": collection,
            "training": training,
            "safety": {
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
            },
        }

    def _background_loop(
        self,
    ) -> None:
        if self.initial_delay_seconds > 0:
            if self._stop_event.wait(
                self.initial_delay_seconds
            ):
                return

        last_training_monotonic = 0.0

        while not self._stop_event.is_set():
            try:
                self.collect_once()

                current_monotonic = time.monotonic()

                if (
                    last_training_monotonic == 0.0
                    or current_monotonic
                    - last_training_monotonic
                    >= self.training_interval_seconds
                ):
                    self.train_once()

                    last_training_monotonic = (
                        current_monotonic
                    )

            except Exception:
                LOGGER.exception(
                    "Échec du cycle automatique Brain V2"
                )

            self._stop_event.wait(
                self.collection_interval_seconds
            )

    def start(
        self,
    ) -> bool:
        with self._lock:
            if not self.enabled:
                self._state["running"] = False
                self._save_state()

                LOGGER.info(
                    "Collecteur automatique Brain V2 désactivé"
                )

                return False

            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return True

            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._background_loop,
                name="brain-v2-auto-collector",
                daemon=True,
            )

            self._thread.start()

            self._state["running"] = True
            self._state["started_at"] = (
                self._utc_now()
            )
            self._state["last_error"] = None

            self._save_state()

            LOGGER.info(
                "Collecteur Brain V2 démarré : collecte=%ss entraînement=%ss",
                self.collection_interval_seconds,
                self.training_interval_seconds,
            )

            return True

    def stop(
        self,
    ) -> None:
        with self._lock:
            self._stop_event.set()

            thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(
                timeout=5
            )

        with self._lock:
            self._state["running"] = False
            self._state["stopped_at"] = (
                self._utc_now()
            )

            self._save_state()

    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            thread_running = bool(
                self._thread is not None
                and self._thread.is_alive()
            )

            status = dict(
                self._state
            )

            status.update(
                {
                    "version": self.VERSION,
                    "enabled": self.enabled,
                    "running": thread_running,
                    "endpoints": list(
                        self.endpoints
                    ),
                    "observations_path": str(
                        self.observations_path
                    ),
                    "state_path": str(
                        self.state_path
                    ),
                    "observations_exists": (
                        self.observations_path.exists()
                    ),
                    "state_exists": (
                        self.state_path.exists()
                    ),
                    "data_directory_writable": (
                        os.access(
                            self.data_directory,
                            os.W_OK,
                        )
                    ),
                    "decision_authority": False,
                    "hardware_control": False,
                    "mqtt_publish": False,
                    "modbus_command": False,
                }
            )

            return status
