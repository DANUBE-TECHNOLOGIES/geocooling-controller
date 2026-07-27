from __future__ import annotations

import copy
import logging
import math
import os
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, text

from app.building.models import (
    BuildingState,
    GeoCoolingTwinState,
    LearningState,
    MeasurementState,
    ThermalState,
    WeatherState,
    ZoneState,
)

logger = logging.getLogger("sbc.building")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_utc(value: datetime | None) -> str | None:
    if value is None:
        return None
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(timezone.utc).isoformat()


def calculate_dew_point(
    temperature: float | None,
    humidity: float | None,
) -> float | None:
    if temperature is None or humidity is None:
        return None
    if humidity <= 0 or humidity > 100:
        return None
    a = 17.62
    b = 243.12
    gamma = math.log(humidity / 100.0) + (
        a * temperature
    ) / (b + temperature)
    return round((b * gamma) / (a - gamma), 3)


class BuildingStateService:
    """Jumeau numérique vivant de la maison.

    PostgreSQL reste l'historien. Ce service construit une vue en mémoire,
    cohérente et thread-safe, destinée aux contrôleurs et aux API.
    """

    SENSOR_ZONE_MAP = {
        "gc_temp_salon": "salon",
        "gc_temp_etage": "etage",
    }

    WEATHER_SENSOR = "weather_outdoor"

    WEATHER_METRICS = (
        "temperature",
        "apparent_temperature",
        "humidity",
        "cloud_cover",
        "precipitation",
        "pressure",
        "wind_speed",
        "wind_gusts",
        "weather_code",
    )

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.refresh_interval_seconds = max(
            1,
            int(os.getenv("BUILDING_REFRESH_INTERVAL_SECONDS", "5")),
        )
        self.indoor_max_age_seconds = max(
            30,
            int(os.getenv("BUILDING_INDOOR_MAX_AGE_SECONDS", "900")),
        )
        self.weather_max_age_seconds = max(
            60,
            int(os.getenv("BUILDING_WEATHER_MAX_AGE_SECONDS", "1800")),
        )
        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None
        self._sequence = 0
        self._last_refresh_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error: str | None = None
        self._refresh_count = 0
        self._state = self._empty_state()

    def _empty_state(self) -> BuildingState:
        return BuildingState(
            inside={
                "salon": ZoneState(name="salon"),
                "etage": ZoneState(name="etage"),
            }
        )

    def start(self) -> None:
        with self._lock:
            if self._worker and self._worker.is_alive():
                return
            self._stop_event.clear()
            self._worker = threading.Thread(
                target=self._run,
                name="building-state-service",
                daemon=True,
            )
            self._worker.start()

    def stop(self) -> None:
        self._stop_event.set()
        worker = self._worker
        if worker and worker.is_alive():
            worker.join(timeout=5)

    def _run(self) -> None:
        while not self._stop_event.is_set():
            try:
                self.refresh()
            except Exception as exc:
                self._last_error = str(exc)
                logger.exception("Échec de rafraîchissement BuildingState")
            self._stop_event.wait(self.refresh_interval_seconds)

    def refresh(self) -> dict[str, Any]:
        now = utc_now()
        state = self._empty_state()

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT DISTINCT ON (sensor_name, metric)
                        sensor_name,
                        metric,
                        value,
                        unit,
                        quality,
                        measured_at,
                        source,
                        mqtt_topic
                    FROM sensor_measurements
                    WHERE sensor_name = ANY(:sensor_names)
                    ORDER BY sensor_name, metric, measured_at DESC
                    """
                ),
                {
                    "sensor_names": [
                        *self.SENSOR_ZONE_MAP.keys(),
                        self.WEATHER_SENSOR,
                    ]
                },
            ).mappings().all()

            thermal_row = connection.execute(
                text(
                    """
                    SELECT
                        calculated_at,
                        indoor_temperature,
                        indoor_humidity,
                        dew_point,
                        slope_1h,
                        slope_3h,
                        outdoor_temperature,
                        indoor_outdoor_delta,
                        data_quality,
                        learning_ready
                    FROM thermal_snapshots
                    ORDER BY calculated_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()

            learning_rows = connection.execute(
                text(
                    """
                    SELECT
                        parameter_name,
                        parameter_value,
                        unit,
                        confidence,
                        sample_count,
                        updated_at,
                        details
                    FROM learning_parameters
                    ORDER BY parameter_name
                    """
                )
            ).mappings().all()

            geocooling_row = connection.execute(
                text(
                    """
                    SELECT
                        created_at,
                        state,
                        mode,
                        valve_open,
                        pump_running,
                        simulation,
                        runtime_seconds,
                        event_type,
                        reason
                    FROM geocooling_state
                    ORDER BY created_at DESC
                    LIMIT 1
                    """
                )
            ).mappings().first()

        lookup: dict[tuple[str, str], Any] = {
            (row["sensor_name"], row["metric"]): row
            for row in rows
        }

        for sensor_name, zone_name in self.SENSOR_ZONE_MAP.items():
            zone = state.inside[zone_name]
            for metric in (
                "temperature",
                "humidity",
                "battery",
                "linkquality",
            ):
                row = lookup.get((sensor_name, metric))
                measurement = self._measurement(
                    row,
                    now,
                    self.indoor_max_age_seconds,
                )
                setattr(zone, metric, measurement)
            zone.dew_point = calculate_dew_point(
                zone.temperature.value,
                zone.humidity.value,
            )
            zone.comfort_temperature = zone.temperature.value
            zone.available = (
                zone.temperature.value is not None
                and zone.temperature.fresh
            )

        weather = WeatherState()
        for metric in self.WEATHER_METRICS:
            row = lookup.get((self.WEATHER_SENSOR, metric))
            setattr(
                weather,
                metric,
                self._measurement(
                    row,
                    now,
                    self.weather_max_age_seconds,
                ),
            )
        weather.available = (
            weather.temperature.value is not None
            and weather.temperature.fresh
        )
        state.outside = weather

        if thermal_row:
            state.thermal = ThermalState(
                indoor_temperature=thermal_row["indoor_temperature"],
                indoor_humidity=thermal_row["indoor_humidity"],
                outdoor_temperature=thermal_row["outdoor_temperature"],
                indoor_outdoor_delta=thermal_row["indoor_outdoor_delta"],
                dew_point=thermal_row["dew_point"],
                slope_1h=thermal_row["slope_1h"],
                slope_3h=thermal_row["slope_3h"],
                data_quality=thermal_row["data_quality"],
                learning_ready=bool(thermal_row["learning_ready"]),
                calculated_at=iso_utc(thermal_row["calculated_at"]),
            )

        if geocooling_row:
            state.geocooling = GeoCoolingTwinState(
                state=geocooling_row["state"],
                mode=geocooling_row["mode"],
                valve_open=bool(geocooling_row["valve_open"]),
                pump_running=bool(geocooling_row["pump_running"]),
                runtime_seconds=int(geocooling_row["runtime_seconds"]),
                simulation=bool(geocooling_row["simulation"]),
                event_type=geocooling_row["event_type"],
                reason=geocooling_row["reason"],
                updated_at=iso_utc(geocooling_row["created_at"]),
            )

        parameters: dict[str, dict[str, Any]] = {}
        total_samples = 0
        for row in learning_rows:
            sample_count = int(row["sample_count"] or 0)
            total_samples += sample_count
            parameters[row["parameter_name"]] = {
                "value": row["parameter_value"],
                "unit": row["unit"],
                "confidence": row["confidence"],
                "sample_count": sample_count,
                "updated_at": iso_utc(row["updated_at"]),
                "details": row["details"] or {},
            }
        state.learning = LearningState(
            status=("learning" if state.thermal.learning_ready else "collecting"),
            parameters=parameters,
            sample_count=total_samples,
            ready=state.thermal.learning_ready,
        )

        indoor_ready = [zone.available for zone in state.inside.values()]
        if all(indoor_ready) and state.outside.available:
            state.status = "ready"
            state.data_quality = "good"
        elif any(indoor_ready):
            state.status = "degraded"
            state.data_quality = "partial"
        else:
            state.status = "waiting_for_data"
            state.data_quality = "missing"

        self._sequence += 1
        state.sequence = self._sequence
        state.generated_at = now.isoformat()
        state.diagnostics = {
            "refresh_interval_seconds": self.refresh_interval_seconds,
            "indoor_max_age_seconds": self.indoor_max_age_seconds,
            "weather_max_age_seconds": self.weather_max_age_seconds,
            "source": "postgresql_historian",
            "sensor_count": len(rows),
        }

        with self._lock:
            self._state = state
            self._last_refresh_at = now.isoformat()
            self._last_success_at = now.isoformat()
            self._last_error = None
            self._refresh_count += 1

        return state.to_dict()

    @staticmethod
    def _measurement(
        row: Any,
        now: datetime,
        max_age_seconds: int,
    ) -> MeasurementState:
        if row is None:
            return MeasurementState()
        measured_at = row["measured_at"]
        if measured_at.tzinfo is None:
            measured_at = measured_at.replace(tzinfo=timezone.utc)
        age_seconds = max(
            0,
            int((now - measured_at.astimezone(timezone.utc)).total_seconds()),
        )
        fresh = age_seconds <= max_age_seconds
        return MeasurementState(
            value=float(row["value"]),
            unit=row["unit"],
            measured_at=iso_utc(measured_at),
            age_seconds=age_seconds,
            quality=row["quality"] if fresh else "stale",
            source=row["source"],
            mqtt_topic=row["mqtt_topic"],
            fresh=fresh,
        )

    def state(self) -> dict[str, Any]:
        with self._lock:
            return copy.deepcopy(self._state.to_dict())

    def inside(self) -> dict[str, Any]:
        return self.state()["inside"]

    def weather(self) -> dict[str, Any]:
        return self.state()["outside"]

    def sensors(self) -> dict[str, Any]:
        state = self.state()
        return {
            "generated_at": state["generated_at"],
            "inside": state["inside"],
            "outside": state["outside"],
        }

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            return {
                "running": bool(self._worker and self._worker.is_alive()),
                "refresh_count": self._refresh_count,
                "last_refresh_at": self._last_refresh_at,
                "last_success_at": self._last_success_at,
                "last_error": self._last_error,
                "sequence": self._sequence,
                "configuration": {
                    "refresh_interval_seconds": self.refresh_interval_seconds,
                    "indoor_max_age_seconds": self.indoor_max_age_seconds,
                    "weather_max_age_seconds": self.weather_max_age_seconds,
                },
            }
