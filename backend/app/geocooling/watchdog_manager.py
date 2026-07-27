"""Watchdog en lecture seule du sous-système GeoCooling.

Le Watchdog analyse les informations déjà disponibles dans le Controller et
le Flight Recorder. Il ne commande jamais les actionneurs et ne modifie aucun
état métier.
"""

from __future__ import annotations

import copy
import os
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


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


def parse_datetime(
    value: Any,
) -> datetime | None:
    if isinstance(value, datetime):
        result = value

    elif isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return None

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            result = datetime.fromisoformat(
                normalized
            )
        except ValueError:
            return None

    else:
        return None

    if result.tzinfo is None:
        result = result.replace(
            tzinfo=timezone.utc
        )

    return result.astimezone(
        timezone.utc
    )


def age_seconds(
    value: Any,
) -> float | None:
    parsed = parse_datetime(value)

    if parsed is None:
        return None

    return max(
        0.0,
        (
            utc_now()
            - parsed
        ).total_seconds(),
    )


class GeoCoolingWatchdog:
    """Analyseur de sécurité et de cohérence en lecture seule."""

    SENSOR_FIELDS = (
        "indoor_temperature_c",
        "indoor_humidity_percent",
        "surface_temperature_c",
        "floor_supply_temperature_c",
        "floor_return_temperature_c",
        "source_inlet_temperature_c",
        "source_outlet_temperature_c",
        "outdoor_temperature_c",
        "flow_rate_l_min",
    )

    def __init__(
        self,
        controller: Any,
        flight_recorder: Any,
        state_cache: Any | None = None,
    ) -> None:
        self.controller = controller
        self.flight_recorder = flight_recorder
        self.state_cache = state_cache

        self.recorder_stale_seconds = env_float(
            "GEOCOOLING_WATCHDOG_RECORDER_STALE_SECONDS",
            default=5.0,
            minimum=2.0,
            maximum=300.0,
        )

        self.thermal_stale_seconds = env_float(
            "GEOCOOLING_WATCHDOG_THERMAL_STALE_SECONDS",
            default=180.0,
            minimum=10.0,
            maximum=3600.0,
        )

        self.sensor_frozen_seconds = env_float(
            "GEOCOOLING_WATCHDOG_SENSOR_FROZEN_SECONDS",
            default=180.0,
            minimum=30.0,
            maximum=3600.0,
        )

        self.minimum_frozen_samples = env_int(
            "GEOCOOLING_WATCHDOG_MIN_FROZEN_SAMPLES",
            default=10,
            minimum=3,
            maximum=300,
        )

        self.sensor_epsilon = env_float(
            "GEOCOOLING_WATCHDOG_SENSOR_EPSILON",
            default=0.01,
            minimum=0.0001,
            maximum=2.0,
        )

        self.minimum_flow_l_min = env_float(
            "GEOCOOLING_WATCHDOG_MIN_FLOW_L_MIN",
            default=1.0,
            minimum=0.0,
            maximum=100.0,
        )

        self.pump_no_flow_seconds = env_float(
            "GEOCOOLING_WATCHDOG_PUMP_NO_FLOW_SECONDS",
            default=15.0,
            minimum=3.0,
            maximum=300.0,
        )

        self.valve_without_pump_seconds = env_float(
            "GEOCOOLING_WATCHDOG_VALVE_WITHOUT_PUMP_SECONDS",
            default=60.0,
            minimum=5.0,
            maximum=600.0,
        )

        self.maximum_controller_errors = env_int(
            "GEOCOOLING_WATCHDOG_MAX_RECENT_ERRORS",
            default=3,
            minimum=1,
            maximum=100,
        )

    def _cached_controller_status(
        self,
    ) -> dict[str, Any]:
        """Lit le Controller via le State Cache avec repli direct."""

        if self.state_cache is not None:
            try:
                snapshot = self.state_cache.latest()

                if isinstance(snapshot, dict):
                    controller_state = snapshot.get("controller")

                    if isinstance(controller_state, dict):
                        return copy.deepcopy(controller_state)

            except Exception:
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
    def _list(
        value: Any,
    ) -> list[Any]:
        if isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return list(value)

        return []

    @staticmethod
    def _alert(
        *,
        code: str,
        severity: str,
        component: str,
        title: str,
        message: str,
        evidence: dict[str, Any] | None = None,
        recommendation: str | None = None,
    ) -> dict[str, Any]:
        normalized_severity = str(
            severity
        ).upper()

        if normalized_severity not in {
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            normalized_severity = "WARNING"

        return {
            "code": code,
            "severity": normalized_severity,
            "component": component,
            "title": title,
            "message": message,
            "evidence": copy.deepcopy(
                evidence or {}
            ),
            "recommendation": recommendation,
        }

    @staticmethod
    def _check(
        *,
        code: str,
        component: str,
        status: str,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(
            status
        ).upper()

        if normalized_status not in {
            "OK",
            "ATTENTION",
            "CRITICAL",
            "UNKNOWN",
        }:
            normalized_status = "UNKNOWN"

        return {
            "code": code,
            "component": component,
            "status": normalized_status,
            "message": message,
            "details": copy.deepcopy(
                details or {}
            ),
        }

    def _controller_status(
        self,
    ) -> tuple[
        dict[str, Any],
        str | None,
    ]:
        try:
            result = self._cached_controller_status()

            if not isinstance(result, dict):
                raise TypeError(
                    "controller.status() invalide."
                )

            return result, None

        except Exception as exc:
            return {}, str(exc)

    def _recorder_status(
        self,
    ) -> tuple[
        dict[str, Any],
        str | None,
    ]:
        try:
            result = self.flight_recorder.status(
                limit=300,
                errors_only=False,
                include_controller=False,
            )

            if not isinstance(result, dict):
                raise TypeError(
                    "flight_recorder.status() invalide."
                )

            return result, None

        except Exception as exc:
            return {}, str(exc)

    @staticmethod
    def _summary(
        snapshot: Any,
    ) -> dict[str, Any]:
        if not isinstance(snapshot, dict):
            return {}

        summary = snapshot.get(
            "summary"
        )

        if isinstance(summary, dict):
            return summary

        return {}

    @staticmethod
    def _snapshot_time(
        snapshot: Any,
    ) -> datetime | None:
        if not isinstance(snapshot, dict):
            return None

        return parse_datetime(
            snapshot.get(
                "captured_at"
            )
        )

    def _continuous_duration(
        self,
        snapshots: list[dict[str, Any]],
        predicate: Any,
    ) -> float:
        matching: list[
            dict[str, Any]
        ] = []

        for snapshot in reversed(
            snapshots
        ):
            summary = self._summary(
                snapshot
            )

            try:
                is_match = bool(
                    predicate(summary)
                )
            except Exception:
                is_match = False

            if not is_match:
                break

            matching.append(snapshot)

        if not matching:
            return 0.0

        newest = self._snapshot_time(
            matching[0]
        )

        oldest = self._snapshot_time(
            matching[-1]
        )

        if newest is None or oldest is None:
            return 0.0

        return max(
            0.0,
            (
                newest
                - oldest
            ).total_seconds(),
        )

    def _sensor_frozen(
        self,
        snapshots: list[
            dict[str, Any]
        ],
        field: str,
    ) -> dict[str, Any] | None:
        samples: list[
            tuple[
                datetime,
                float,
            ]
        ] = []

        for snapshot in snapshots:
            if not snapshot.get(
                "success",
                False,
            ):
                continue

            captured_at = self._snapshot_time(
                snapshot
            )

            if captured_at is None:
                continue

            value = self._summary(
                snapshot
            ).get(field)

            if isinstance(value, bool):
                continue

            if not isinstance(
                value,
                (
                    int,
                    float,
                ),
            ):
                continue

            samples.append(
                (
                    captured_at,
                    float(value),
                )
            )

        if len(samples) < (
            self.minimum_frozen_samples
        ):
            return None

        newest_at = samples[-1][0]
        minimum_time = (
            newest_at.timestamp()
            - self.sensor_frozen_seconds
        )

        window = [
            sample
            for sample in samples
            if sample[0].timestamp()
            >= minimum_time
        ]

        if len(window) < (
            self.minimum_frozen_samples
        ):
            return None

        duration = (
            window[-1][0]
            - window[0][0]
        ).total_seconds()

        if duration < (
            self.sensor_frozen_seconds
            * 0.8
        ):
            return None

        values = [
            item[1]
            for item in window
        ]

        variation = max(values) - min(values)

        if variation > self.sensor_epsilon:
            return None

        return {
            "field": field,
            "samples": len(window),
            "duration_seconds": round(
                duration,
                3,
            ),
            "minimum": min(values),
            "maximum": max(values),
            "variation": round(
                variation,
                6,
            ),
            "epsilon": self.sensor_epsilon,
        }

    def evaluate(self) -> dict[str, Any]:
        generated_at = utc_now_iso()

        controller_status, controller_error = (
            self._controller_status()
        )

        recorder_status, recorder_error = (
            self._recorder_status()
        )

        recorder_meta = self._mapping(
            recorder_status.get(
                "recorder"
            )
        )

        snapshots = [
            item
            for item in self._list(
                recorder_status.get(
                    "snapshots"
                )
            )
            if isinstance(item, dict)
        ]

        latest_snapshot = (
            snapshots[-1]
            if snapshots
            else {}
        )

        latest_summary = self._summary(
            latest_snapshot
        )

        checks: list[
            dict[str, Any]
        ] = []

        alerts: list[
            dict[str, Any]
        ] = []

        #######################################################################
        # CONTROLLER
        #######################################################################

        if controller_error:
            checks.append(
                self._check(
                    code="controller_access",
                    component="controller",
                    status="CRITICAL",
                    message=(
                        "Le Controller ne peut pas être lu."
                    ),
                    details={
                        "error": controller_error,
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="CONTROLLER_UNAVAILABLE",
                    severity="CRITICAL",
                    component="controller",
                    title="Controller indisponible",
                    message=controller_error,
                    recommendation=(
                        "Contrôler les logs backend et "
                        "l'initialisation GeoCooling."
                    ),
                )
            )

        else:
            controller_state = str(
                controller_status.get(
                    "state",
                    "UNKNOWN",
                )
            ).upper()

            checks.append(
                self._check(
                    code="controller_access",
                    component="controller",
                    status="OK",
                    message=(
                        "Controller lisible."
                    ),
                    details={
                        "state": controller_state,
                        "mode": controller_status.get(
                            "mode"
                        ),
                    },
                )
            )

            last_error = controller_status.get(
                "last_error"
            )

            if last_error:
                alerts.append(
                    self._alert(
                        code="CONTROLLER_LAST_ERROR",
                        severity="WARNING",
                        component="controller",
                        title=(
                            "Erreur récente du Controller"
                        ),
                        message=str(last_error),
                        evidence={
                            "state": controller_state,
                            "last_event": (
                                controller_status.get(
                                    "last_event"
                                )
                            ),
                            "last_reason": (
                                controller_status.get(
                                    "last_reason"
                                )
                            ),
                        },
                        recommendation=(
                            "Consulter l'Event Timeline "
                            "et le Flight Recorder."
                        ),
                    )
                )

        #######################################################################
        # FLIGHT RECORDER
        #######################################################################

        if recorder_error:
            checks.append(
                self._check(
                    code="flight_recorder",
                    component="flight_recorder",
                    status="CRITICAL",
                    message=(
                        "Flight Recorder inaccessible."
                    ),
                    details={
                        "error": recorder_error,
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="FLIGHT_RECORDER_UNAVAILABLE",
                    severity="CRITICAL",
                    component="flight_recorder",
                    title=(
                        "Flight Recorder indisponible"
                    ),
                    message=recorder_error,
                    recommendation=(
                        "Contrôler le backend et C004."
                    ),
                )
            )

        else:
            recorder_running = bool(
                recorder_status.get(
                    "running",
                    False,
                )
            )

            last_capture_age = age_seconds(
                recorder_meta.get(
                    "last_capture_at"
                )
            )

            if not recorder_running:
                recorder_check_status = (
                    "CRITICAL"
                )
                recorder_message = (
                    "Flight Recorder déclaré arrêté."
                )

                alerts.append(
                    self._alert(
                        code="FLIGHT_RECORDER_STOPPED",
                        severity="CRITICAL",
                        component="flight_recorder",
                        title=(
                            "Flight Recorder arrêté"
                        ),
                        message=recorder_message,
                        evidence={
                            "last_capture_at": (
                                recorder_meta.get(
                                    "last_capture_at"
                                )
                            ),
                        },
                        recommendation=(
                            "Redémarrer le backend après "
                            "analyse des logs."
                        ),
                    )
                )

            elif (
                last_capture_age is None
                or last_capture_age
                > self.recorder_stale_seconds
            ):
                recorder_check_status = (
                    "CRITICAL"
                )
                recorder_message = (
                    "Les captures du Flight Recorder "
                    "ne progressent plus."
                )

                alerts.append(
                    self._alert(
                        code="FLIGHT_RECORDER_STALE",
                        severity="CRITICAL",
                        component="flight_recorder",
                        title=(
                            "Flight Recorder figé"
                        ),
                        message=recorder_message,
                        evidence={
                            "last_capture_at": (
                                recorder_meta.get(
                                    "last_capture_at"
                                )
                            ),
                            "age_seconds": (
                                last_capture_age
                            ),
                            "threshold_seconds": (
                                self.recorder_stale_seconds
                            ),
                        },
                        recommendation=(
                            "Contrôler le thread du "
                            "Flight Recorder via sa "
                            "progression API et les logs."
                        ),
                    )
                )

            else:
                recorder_check_status = "OK"
                recorder_message = (
                    "Flight Recorder actif et récent."
                )

            checks.append(
                self._check(
                    code="flight_recorder",
                    component="flight_recorder",
                    status=recorder_check_status,
                    message=recorder_message,
                    details={
                        "running": recorder_running,
                        "capture_count": (
                            recorder_meta.get(
                                "capture_count"
                            )
                        ),
                        "stored_count": (
                            recorder_meta.get(
                                "stored_count"
                            )
                        ),
                        "last_capture_at": (
                            recorder_meta.get(
                                "last_capture_at"
                            )
                        ),
                        "age_seconds": (
                            last_capture_age
                        ),
                    },
                )
            )

            error_count = int(
                recorder_meta.get(
                    "error_count",
                    0,
                )
                or 0
            )

            if error_count >= (
                self.maximum_controller_errors
            ):
                alerts.append(
                    self._alert(
                        code=(
                            "FLIGHT_RECORDER_REPEATED_ERRORS"
                        ),
                        severity="WARNING",
                        component="flight_recorder",
                        title=(
                            "Erreurs répétées de capture"
                        ),
                        message=(
                            f"{error_count} erreurs ont été "
                            "enregistrées."
                        ),
                        evidence={
                            "error_count": error_count,
                            "last_error": (
                                recorder_meta.get(
                                    "last_error"
                                )
                            ),
                        },
                        recommendation=(
                            "Analyser les erreurs de "
                            "controller.status()."
                        ),
                    )
                )

        #######################################################################
        # MQTT / DRIVER / ESP32
        #######################################################################

        driver = self._mapping(
            controller_status.get(
                "driver"
            )
        )

        device = self._mapping(
            controller_status.get(
                "device"
            )
        )

        driver_connected = (
            latest_summary.get(
                "driver_connected"
            )
        )

        if driver_connected is None:
            driver_connected = driver.get(
                "connected"
            )

        device_online = (
            latest_summary.get(
                "device_online"
            )
        )

        if device_online is None:
            device_online = device.get(
                "online",
                driver.get(
                    "device_online"
                ),
            )

        heartbeat_fresh = (
            latest_summary.get(
                "heartbeat_fresh"
            )
        )

        if heartbeat_fresh is None:
            heartbeat_fresh = device.get(
                "heartbeat_fresh"
            )

        simulation = bool(
            controller_status.get(
                "simulation",
                latest_summary.get(
                    "simulation",
                    False,
                ),
            )
        )

        if simulation:
            checks.append(
                self._check(
                    code="mqtt_driver",
                    component="driver",
                    status="OK",
                    message=(
                        "Mode simulation : connexion "
                        "matérielle non exigée."
                    ),
                    details={
                        "simulation": True,
                        "driver_connected": (
                            driver_connected
                        ),
                    },
                )
            )

            checks.append(
                self._check(
                    code="esp32_heartbeat",
                    component="esp32",
                    status="OK",
                    message=(
                        "Mode simulation : heartbeat "
                        "physique non exigé."
                    ),
                    details={
                        "simulation": True,
                    },
                )
            )

        else:
            if driver_connected is False:
                checks.append(
                    self._check(
                        code="mqtt_driver",
                        component="driver",
                        status="CRITICAL",
                        message=(
                            "Connexion Driver/MQTT perdue."
                        ),
                    )
                )

                alerts.append(
                    self._alert(
                        code="MQTT_DRIVER_DISCONNECTED",
                        severity="CRITICAL",
                        component="driver",
                        title=(
                            "Connexion MQTT perdue"
                        ),
                        message=(
                            "Le Driver ne déclare plus "
                            "de connexion active."
                        ),
                        evidence={
                            "driver": driver,
                        },
                        recommendation=(
                            "Contrôler Mosquitto, le réseau "
                            "et les paramètres MQTT."
                        ),
                    )
                )

            elif driver_connected is True:
                checks.append(
                    self._check(
                        code="mqtt_driver",
                        component="driver",
                        status="OK",
                        message=(
                            "Connexion Driver/MQTT active."
                        ),
                    )
                )

            else:
                checks.append(
                    self._check(
                        code="mqtt_driver",
                        component="driver",
                        status="UNKNOWN",
                        message=(
                            "État de connexion MQTT inconnu."
                        ),
                    )
                )

            esp32_problem = (
                device_online is False
                or heartbeat_fresh is False
            )

            if esp32_problem:
                checks.append(
                    self._check(
                        code="esp32_heartbeat",
                        component="esp32",
                        status="CRITICAL",
                        message=(
                            "ESP32 hors ligne ou heartbeat "
                            "périmé."
                        ),
                        details={
                            "device_online": device_online,
                            "heartbeat_fresh": (
                                heartbeat_fresh
                            ),
                        },
                    )
                )

                alerts.append(
                    self._alert(
                        code="ESP32_HEARTBEAT_LOST",
                        severity="CRITICAL",
                        component="esp32",
                        title=(
                            "Communication ESP32 perdue"
                        ),
                        message=(
                            "L'ESP32 est déclaré hors ligne "
                            "ou son heartbeat est périmé."
                        ),
                        evidence={
                            "device_online": device_online,
                            "heartbeat_fresh": (
                                heartbeat_fresh
                            ),
                            "device": device,
                        },
                        recommendation=(
                            "Contrôler alimentation, "
                            "Ethernet, MQTT et firmware."
                        ),
                    )
                )

            elif (
                device_online is True
                and heartbeat_fresh is True
            ):
                checks.append(
                    self._check(
                        code="esp32_heartbeat",
                        component="esp32",
                        status="OK",
                        message=(
                            "ESP32 en ligne et heartbeat "
                            "récent."
                        ),
                    )
                )

            else:
                checks.append(
                    self._check(
                        code="esp32_heartbeat",
                        component="esp32",
                        status="UNKNOWN",
                        message=(
                            "État ESP32 incomplet."
                        ),
                        details={
                            "device_online": device_online,
                            "heartbeat_fresh": (
                                heartbeat_fresh
                            ),
                        },
                    )
                )

        #######################################################################
        # DONNÉES THERMIQUES
        #######################################################################

        thermal_timestamp = latest_summary.get(
            "thermal_timestamp"
        )

        thermal_age = age_seconds(
            thermal_timestamp
        )

        if thermal_timestamp is None:
            checks.append(
                self._check(
                    code="thermal_freshness",
                    component="thermal",
                    status="ATTENTION",
                    message=(
                        "Horodatage thermique absent."
                    ),
                )
            )

            alerts.append(
                self._alert(
                    code="THERMAL_TIMESTAMP_MISSING",
                    severity="WARNING",
                    component="thermal",
                    title=(
                        "Horodatage thermique absent"
                    ),
                    message=(
                        "La fraîcheur des données "
                        "thermiques ne peut pas être "
                        "garantie."
                    ),
                    recommendation=(
                        "Contrôler la publication des "
                        "sondes et le mapping thermique."
                    ),
                )
            )

        elif (
            thermal_age is not None
            and thermal_age
            > self.thermal_stale_seconds
        ):
            checks.append(
                self._check(
                    code="thermal_freshness",
                    component="thermal",
                    status="CRITICAL",
                    message=(
                        "Données thermiques périmées."
                    ),
                    details={
                        "timestamp": thermal_timestamp,
                        "age_seconds": thermal_age,
                        "threshold_seconds": (
                            self.thermal_stale_seconds
                        ),
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="THERMAL_DATA_STALE",
                    severity="CRITICAL",
                    component="thermal",
                    title=(
                        "Données thermiques périmées"
                    ),
                    message=(
                        "Aucune donnée thermique récente "
                        "n'est disponible."
                    ),
                    evidence={
                        "timestamp": thermal_timestamp,
                        "age_seconds": thermal_age,
                        "threshold_seconds": (
                            self.thermal_stale_seconds
                        ),
                    },
                    recommendation=(
                        "Contrôler les sondes, MQTT et "
                        "l'horodatage des mesures."
                    ),
                )
            )

        else:
            checks.append(
                self._check(
                    code="thermal_freshness",
                    component="thermal",
                    status="OK",
                    message=(
                        "Données thermiques récentes."
                    ),
                    details={
                        "timestamp": thermal_timestamp,
                        "age_seconds": thermal_age,
                    },
                )
            )

        frozen_sensors: list[
            dict[str, Any]
        ] = []

        for field in self.SENSOR_FIELDS:
            result = self._sensor_frozen(
                snapshots,
                field,
            )

            if result is not None:
                frozen_sensors.append(result)

        if frozen_sensors:
            checks.append(
                self._check(
                    code="sensor_variation",
                    component="thermal",
                    status="ATTENTION",
                    message=(
                        "Une ou plusieurs sondes semblent "
                        "figées."
                    ),
                    details={
                        "frozen_sensors": (
                            frozen_sensors
                        ),
                    },
                )
            )

            for frozen in frozen_sensors:
                alerts.append(
                    self._alert(
                        code=(
                            "SENSOR_FROZEN_"
                            + str(
                                frozen["field"]
                            ).upper()
                        ),
                        severity="WARNING",
                        component="thermal",
                        title=(
                            "Sonde potentiellement figée"
                        ),
                        message=(
                            f"La valeur "
                            f"{frozen['field']} n'a presque "
                            f"pas varié pendant "
                            f"{frozen['duration_seconds']} s."
                        ),
                        evidence=frozen,
                        recommendation=(
                            "Comparer avec une mesure "
                            "physique et contrôler le bus "
                            "de sondes."
                        ),
                    )
                )

        else:
            checks.append(
                self._check(
                    code="sensor_variation",
                    component="thermal",
                    status="OK",
                    message=(
                        "Aucune sonde figée détectée dans "
                        "la fenêtre disponible."
                    ),
                    details={
                        "minimum_samples": (
                            self.minimum_frozen_samples
                        ),
                        "window_seconds": (
                            self.sensor_frozen_seconds
                        ),
                    },
                )
            )

        #######################################################################
        # POMPE / DÉBIT / VANNE
        #######################################################################

        pump_running = latest_summary.get(
            "pump_running"
        )

        valve_open = latest_summary.get(
            "valve_open"
        )

        flow_rate = latest_summary.get(
            "flow_rate_l_min"
        )

        pump_without_valve = (
            pump_running is True
            and valve_open is not True
        )

        if pump_without_valve:
            checks.append(
                self._check(
                    code="pump_valve_coherence",
                    component="hydraulic",
                    status="CRITICAL",
                    message=(
                        "Circulateur actif sans vanne "
                        "confirmée ouverte."
                    ),
                )
            )

            alerts.append(
                self._alert(
                    code="PUMP_RUNNING_WITH_VALVE_CLOSED",
                    severity="CRITICAL",
                    component="hydraulic",
                    title=(
                        "Incohérence pompe / vanne"
                    ),
                    message=(
                        "Le circulateur est annoncé actif "
                        "alors que la vanne n'est pas "
                        "confirmée ouverte."
                    ),
                    evidence={
                        "pump_running": pump_running,
                        "valve_open": valve_open,
                    },
                    recommendation=(
                        "Arrêter les essais et contrôler "
                        "les retours d'état et relais."
                    ),
                )
            )

        else:
            checks.append(
                self._check(
                    code="pump_valve_coherence",
                    component="hydraulic",
                    status="OK",
                    message=(
                        "Aucune incohérence immédiate "
                        "pompe / vanne."
                    ),
                    details={
                        "pump_running": pump_running,
                        "valve_open": valve_open,
                    },
                )
            )

        pump_no_flow_duration = (
            self._continuous_duration(
                snapshots,
                lambda summary: (
                    summary.get(
                        "pump_running"
                    )
                    is True
                    and isinstance(
                        summary.get(
                            "flow_rate_l_min"
                        ),
                        (
                            int,
                            float,
                        ),
                    )
                    and float(
                        summary.get(
                            "flow_rate_l_min"
                        )
                    )
                    < self.minimum_flow_l_min
                ),
            )
        )

        if (
            pump_no_flow_duration
            >= self.pump_no_flow_seconds
        ):
            checks.append(
                self._check(
                    code="pump_flow",
                    component="hydraulic",
                    status="CRITICAL",
                    message=(
                        "Circulateur actif sans débit "
                        "suffisant."
                    ),
                    details={
                        "duration_seconds": (
                            pump_no_flow_duration
                        ),
                        "flow_rate_l_min": flow_rate,
                        "minimum_flow_l_min": (
                            self.minimum_flow_l_min
                        ),
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="PUMP_RUNNING_WITHOUT_FLOW",
                    severity="CRITICAL",
                    component="hydraulic",
                    title=(
                        "Circulateur actif sans débit"
                    ),
                    message=(
                        "Le débit reste inférieur au seuil "
                        "alors que le circulateur est actif."
                    ),
                    evidence={
                        "duration_seconds": (
                            pump_no_flow_duration
                        ),
                        "flow_rate_l_min": flow_rate,
                        "minimum_flow_l_min": (
                            self.minimum_flow_l_min
                        ),
                    },
                    recommendation=(
                        "Contrôler vanne, circulateur, "
                        "purge, filtre et capteur de débit."
                    ),
                )
            )

        elif pump_running is True:
            checks.append(
                self._check(
                    code="pump_flow",
                    component="hydraulic",
                    status="OK",
                    message=(
                        "Aucune absence prolongée de débit "
                        "détectée."
                    ),
                    details={
                        "flow_rate_l_min": flow_rate,
                        "duration_seconds": (
                            pump_no_flow_duration
                        ),
                    },
                )
            )

        else:
            checks.append(
                self._check(
                    code="pump_flow",
                    component="hydraulic",
                    status="OK",
                    message=(
                        "Circulateur arrêté : contrôle de "
                        "débit non requis."
                    ),
                )
            )

        valve_without_pump_duration = (
            self._continuous_duration(
                snapshots,
                lambda summary: (
                    summary.get(
                        "valve_open"
                    )
                    is True
                    and summary.get(
                        "pump_running"
                    )
                    is not True
                ),
            )
        )

        if (
            valve_without_pump_duration
            >= self.valve_without_pump_seconds
        ):
            checks.append(
                self._check(
                    code="valve_duration",
                    component="hydraulic",
                    status="ATTENTION",
                    message=(
                        "Vanne ouverte durablement sans "
                        "circulateur."
                    ),
                    details={
                        "duration_seconds": (
                            valve_without_pump_duration
                        ),
                        "threshold_seconds": (
                            self.valve_without_pump_seconds
                        ),
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="VALVE_OPEN_WITHOUT_PUMP",
                    severity="WARNING",
                    component="hydraulic",
                    title=(
                        "Vanne ouverte sans circulateur"
                    ),
                    message=(
                        "La vanne reste ouverte alors que "
                        "le circulateur est arrêté."
                    ),
                    evidence={
                        "duration_seconds": (
                            valve_without_pump_duration
                        ),
                        "threshold_seconds": (
                            self.valve_without_pump_seconds
                        ),
                    },
                    recommendation=(
                        "Vérifier qu'aucun test de "
                        "commissioning n'est actif et "
                        "contrôler le retour de vanne."
                    ),
                )
            )

        else:
            checks.append(
                self._check(
                    code="valve_duration",
                    component="hydraulic",
                    status="OK",
                    message=(
                        "Aucune ouverture anormalement "
                        "longue de la vanne détectée."
                    ),
                    details={
                        "duration_seconds": (
                            valve_without_pump_duration
                        ),
                    },
                )
            )

        #######################################################################
        # SÉCURITÉ THERMIQUE
        #######################################################################

        safety_safe = latest_summary.get(
            "safety_safe"
        )

        safety_level = str(
            latest_summary.get(
                "safety_level",
                "UNKNOWN",
            )
        ).upper()

        if (
            safety_safe is False
            or safety_level
            in {
                "CRITICAL",
                "DANGER",
                "UNSAFE",
                "ERROR",
            }
        ):
            checks.append(
                self._check(
                    code="thermal_safety",
                    component="safety",
                    status="CRITICAL",
                    message=(
                        "Sécurité thermique non satisfaite."
                    ),
                    details={
                        "safe": safety_safe,
                        "level": safety_level,
                        "dew_point_c": (
                            latest_summary.get(
                                "dew_point_c"
                            )
                        ),
                        "safety_margin_c": (
                            latest_summary.get(
                                "safety_margin_c"
                            )
                        ),
                    },
                )
            )

            alerts.append(
                self._alert(
                    code="THERMAL_SAFETY_UNSAFE",
                    severity="CRITICAL",
                    component="safety",
                    title=(
                        "Sécurité thermique critique"
                    ),
                    message=(
                        "Le système indique une condition "
                        "thermique non sûre."
                    ),
                    evidence={
                        "safe": safety_safe,
                        "level": safety_level,
                        "dew_point_c": (
                            latest_summary.get(
                                "dew_point_c"
                            )
                        ),
                        "safety_margin_c": (
                            latest_summary.get(
                                "safety_margin_c"
                            )
                        ),
                    },
                    recommendation=(
                        "Ne pas démarrer le geocooling "
                        "avant résolution."
                    ),
                )
            )

        elif safety_safe is True:
            checks.append(
                self._check(
                    code="thermal_safety",
                    component="safety",
                    status="OK",
                    message=(
                        "Sécurité thermique satisfaite."
                    ),
                    details={
                        "level": safety_level,
                        "dew_point_c": (
                            latest_summary.get(
                                "dew_point_c"
                            )
                        ),
                        "safety_margin_c": (
                            latest_summary.get(
                                "safety_margin_c"
                            )
                        ),
                    },
                )
            )

        else:
            checks.append(
                self._check(
                    code="thermal_safety",
                    component="safety",
                    status="UNKNOWN",
                    message=(
                        "État de sécurité thermique "
                        "incomplet."
                    ),
                    details={
                        "safe": safety_safe,
                        "level": safety_level,
                    },
                )
            )

        #######################################################################
        # SYNTHÈSE
        #######################################################################

        severity_order = {
            "INFO": 0,
            "WARNING": 1,
            "ERROR": 2,
            "CRITICAL": 3,
        }

        alerts.sort(
            key=lambda item: (
                severity_order.get(
                    item.get(
                        "severity",
                        "INFO",
                    ),
                    0,
                ),
                item.get(
                    "component",
                    "",
                ),
                item.get(
                    "code",
                    "",
                ),
            ),
            reverse=True,
        )

        severity_counts = {
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
        }

        for alert in alerts:
            severity = alert.get(
                "severity",
                "WARNING",
            )

            severity_counts[severity] = (
                severity_counts.get(
                    severity,
                    0,
                )
                + 1
            )

        if severity_counts["CRITICAL"] > 0:
            overall = "CRITICAL"

        elif (
            severity_counts["ERROR"] > 0
            or severity_counts["WARNING"] > 0
        ):
            overall = "ATTENTION"

        else:
            overall = "OK"

        return {
            "component": "geocooling",
            "view": "watchdog",
            "generated_at": generated_at,
            "read_only": True,
            "overall": overall,
            "simulation": simulation,
            "summary": {
                "checks": len(checks),
                "active_alerts": len(alerts),
                "severity_counts": severity_counts,
                "critical": (
                    severity_counts["CRITICAL"]
                ),
                "warning": (
                    severity_counts["WARNING"]
                ),
            },
            "thresholds": {
                "recorder_stale_seconds": (
                    self.recorder_stale_seconds
                ),
                "thermal_stale_seconds": (
                    self.thermal_stale_seconds
                ),
                "sensor_frozen_seconds": (
                    self.sensor_frozen_seconds
                ),
                "minimum_frozen_samples": (
                    self.minimum_frozen_samples
                ),
                "sensor_epsilon": (
                    self.sensor_epsilon
                ),
                "minimum_flow_l_min": (
                    self.minimum_flow_l_min
                ),
                "pump_no_flow_seconds": (
                    self.pump_no_flow_seconds
                ),
                "valve_without_pump_seconds": (
                    self.valve_without_pump_seconds
                ),
            },
            "observations": {
                "controller_state": (
                    controller_status.get(
                        "state"
                    )
                ),
                "controller_mode": (
                    controller_status.get(
                        "mode"
                    )
                ),
                "driver_connected": (
                    driver_connected
                ),
                "device_online": device_online,
                "heartbeat_fresh": (
                    heartbeat_fresh
                ),
                "pump_running": pump_running,
                "valve_open": valve_open,
                "flow_rate_l_min": flow_rate,
                "thermal_timestamp": (
                    thermal_timestamp
                ),
                "thermal_age_seconds": (
                    thermal_age
                ),
                "safety_safe": safety_safe,
                "safety_level": safety_level,
                "flight_recorder_running": (
                    recorder_status.get(
                        "running"
                    )
                ),
                "flight_recorder_last_capture": (
                    recorder_meta.get(
                        "last_capture_at"
                    )
                ),
            },
            "checks": checks,
            "alerts": alerts,
        }

    def alerts(self) -> dict[str, Any]:
        result = self.evaluate()

        return {
            "component": "geocooling",
            "view": "watchdog_alerts",
            "generated_at": utc_now_iso(),
            "read_only": True,
            "overall": result["overall"],
            "summary": result["summary"],
            "alerts": result["alerts"],
        }
