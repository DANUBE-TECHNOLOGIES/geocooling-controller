import json
import logging
import math
import os
import threading
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


logger = logging.getLogger("sbc.weather")

WEATHER_PROVIDER = os.getenv(
    "WEATHER_PROVIDER",
    "open_meteo",
)

WEATHER_LATITUDE = float(
    os.getenv("WEATHER_LATITUDE", "48.131487")
)

WEATHER_LONGITUDE = float(
    os.getenv("WEATHER_LONGITUDE", "2.859585")
)

WEATHER_TIMEZONE = os.getenv(
    "WEATHER_TIMEZONE",
    "Europe/Paris",
)

WEATHER_REFRESH_SECONDS = max(
    300,
    int(os.getenv("WEATHER_REFRESH_SECONDS", "900")),
)

WEATHER_FORECAST_DAYS = min(
    7,
    max(
        2,
        int(os.getenv("WEATHER_FORECAST_DAYS", "4")),
    ),
)

WEATHER_TIMEOUT_SECONDS = max(
    5,
    int(os.getenv("WEATHER_TIMEOUT_SECONDS", "30")),
)

OPEN_METEO_FORECAST_URL = (
    "https://api.open-meteo.com/v1/forecast"
)

CURRENT_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "is_day",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
]

HOURLY_VARIABLES = [
    "temperature_2m",
    "relative_humidity_2m",
    "dew_point_2m",
    "apparent_temperature",
    "precipitation_probability",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "visibility",
    "surface_pressure",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
    "direct_normal_irradiance",
    "sunshine_duration",
]

UNITS = {
    "temperature_2m": "°C",
    "relative_humidity_2m": "%",
    "dew_point_2m": "°C",
    "apparent_temperature": "°C",
    "precipitation_probability": "%",
    "precipitation": "mm",
    "rain": "mm",
    "weather_code": "wmo",
    "cloud_cover": "%",
    "visibility": "m",
    "surface_pressure": "hPa",
    "wind_speed_10m": "km/h",
    "wind_direction_10m": "°",
    "wind_gusts_10m": "km/h",
    "shortwave_radiation": "W/m²",
    "direct_radiation": "W/m²",
    "diffuse_radiation": "W/m²",
    "direct_normal_irradiance": "W/m²",
    "sunshine_duration": "s",
    "is_day": "boolean",
}

NORMALIZED_CURRENT_METRICS = {
    "temperature_2m": "temperature",
    "relative_humidity_2m": "humidity",
    "apparent_temperature": "apparent_temperature",
    "precipitation": "precipitation",
    "rain": "rain",
    "weather_code": "weather_code",
    "cloud_cover": "cloud_cover",
    "surface_pressure": "pressure",
    "wind_speed_10m": "wind_speed",
    "wind_direction_10m": "wind_direction",
    "wind_gusts_10m": "wind_gusts",
    "is_day": "is_day",
}


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(value: str) -> datetime:
    parsed = datetime.fromisoformat(value)

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def safe_number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(int(value))

    if not isinstance(value, (int, float)):
        return None

    converted = float(value)

    if not math.isfinite(converted):
        return None

    return converted


class WeatherService:
    def __init__(self, engine: Any) -> None:
        self.engine = engine
        self.stop_event = threading.Event()

        self.running = False
        self.last_attempt_at: str | None = None
        self.last_success_at: str | None = None
        self.last_error: str | None = None

        self.current_temperature: float | None = None
        self.current_humidity: float | None = None
        self.forecast_count = 0
        self.refresh_count = 0

    def initialize_database(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS weather_observations (
                id BIGSERIAL PRIMARY KEY,

                observed_at TIMESTAMPTZ NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                provider TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,

                temperature DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                apparent_temperature DOUBLE PRECISION,

                is_day BOOLEAN,

                precipitation DOUBLE PRECISION,
                rain DOUBLE PRECISION,

                weather_code INTEGER,
                cloud_cover DOUBLE PRECISION,
                surface_pressure DOUBLE PRECISION,

                wind_speed DOUBLE PRECISION,
                wind_direction DOUBLE PRECISION,
                wind_gusts DOUBLE PRECISION,

                raw_data JSONB NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_weather_observations_provider_time
            ON weather_observations (
                provider,
                observed_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_weather_observations_time
            ON weather_observations (
                observed_at DESC
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS weather_forecasts (
                id BIGSERIAL PRIMARY KEY,

                forecast_at TIMESTAMPTZ NOT NULL,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),

                provider TEXT NOT NULL,
                latitude DOUBLE PRECISION NOT NULL,
                longitude DOUBLE PRECISION NOT NULL,

                temperature DOUBLE PRECISION,
                humidity DOUBLE PRECISION,
                dew_point DOUBLE PRECISION,
                apparent_temperature DOUBLE PRECISION,

                precipitation_probability DOUBLE PRECISION,
                precipitation DOUBLE PRECISION,
                rain DOUBLE PRECISION,

                weather_code INTEGER,
                cloud_cover DOUBLE PRECISION,
                visibility DOUBLE PRECISION,
                surface_pressure DOUBLE PRECISION,

                wind_speed DOUBLE PRECISION,
                wind_direction DOUBLE PRECISION,
                wind_gusts DOUBLE PRECISION,

                shortwave_radiation DOUBLE PRECISION,
                direct_radiation DOUBLE PRECISION,
                diffuse_radiation DOUBLE PRECISION,
                direct_normal_irradiance DOUBLE PRECISION,
                sunshine_duration DOUBLE PRECISION,

                raw_data JSONB NOT NULL
            )
            """,
            """
            CREATE UNIQUE INDEX IF NOT EXISTS
                uq_weather_forecasts_provider_time
            ON weather_forecasts (
                provider,
                forecast_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_weather_forecasts_time
            ON weather_forecasts (
                forecast_at
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS
                idx_weather_forecasts_fetched
            ON weather_forecasts (
                fetched_at DESC
            )
            """,
            """
            CREATE TABLE IF NOT EXISTS weather_fetch_history (
                id BIGSERIAL PRIMARY KEY,
                fetched_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                provider TEXT NOT NULL,
                successful BOOLEAN NOT NULL,
                forecast_count INTEGER NOT NULL DEFAULT 0,
                duration_ms DOUBLE PRECISION,
                error_message TEXT
            )
            """,
        ]

        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def build_url(self) -> str:
        parameters = {
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
            "current": ",".join(CURRENT_VARIABLES),
            "hourly": ",".join(HOURLY_VARIABLES),
            "forecast_days": WEATHER_FORECAST_DAYS,
            "timezone": "UTC",
            "timeformat": "iso8601",
            "wind_speed_unit": "kmh",
            "temperature_unit": "celsius",
            "precipitation_unit": "mm",
        }

        return (
            OPEN_METEO_FORECAST_URL
            + "?"
            + urllib.parse.urlencode(parameters)
        )

    def fetch_weather(self) -> dict[str, Any]:
        request = urllib.request.Request(
            self.build_url(),
            headers={
                "Accept": "application/json",
                "User-Agent": (
                    "Smart-Building-Controller/0.3"
                ),
            },
        )

        with urllib.request.urlopen(
            request,
            timeout=WEATHER_TIMEOUT_SECONDS,
        ) as response:
            if response.status != 200:
                raise RuntimeError(
                    f"Réponse météo HTTP {response.status}"
                )

            payload = json.loads(
                response.read().decode("utf-8")
            )

        if "current" not in payload:
            raise RuntimeError(
                "La réponse météo ne contient pas "
                "les conditions actuelles"
            )

        if "hourly" not in payload:
            raise RuntimeError(
                "La réponse météo ne contient pas "
                "les prévisions horaires"
            )

        return payload

    def store_current(
        self,
        connection: Any,
        payload: dict[str, Any],
    ) -> None:
        current = payload.get("current") or {}

        observed_time = current.get("time")

        if not observed_time:
            raise RuntimeError(
                "Heure météo actuelle absente"
            )

        observed_at = parse_datetime(observed_time)

        temperature = safe_number(
            current.get("temperature_2m")
        )

        humidity = safe_number(
            current.get("relative_humidity_2m")
        )

        is_day_value = current.get("is_day")

        is_day = (
            bool(is_day_value)
            if is_day_value is not None
            else None
        )

        parameters = {
            "observed_at": observed_at,
            "provider": WEATHER_PROVIDER,
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
            "temperature": temperature,
            "humidity": humidity,
            "apparent_temperature": safe_number(
                current.get("apparent_temperature")
            ),
            "is_day": is_day,
            "precipitation": safe_number(
                current.get("precipitation")
            ),
            "rain": safe_number(
                current.get("rain")
            ),
            "weather_code": current.get("weather_code"),
            "cloud_cover": safe_number(
                current.get("cloud_cover")
            ),
            "surface_pressure": safe_number(
                current.get("surface_pressure")
            ),
            "wind_speed": safe_number(
                current.get("wind_speed_10m")
            ),
            "wind_direction": safe_number(
                current.get("wind_direction_10m")
            ),
            "wind_gusts": safe_number(
                current.get("wind_gusts_10m")
            ),
            "raw_data": json.dumps(
                current,
                ensure_ascii=False,
            ),
        }

        connection.execute(
            text(
                """
                INSERT INTO weather_observations (
                    observed_at,
                    provider,
                    latitude,
                    longitude,
                    temperature,
                    humidity,
                    apparent_temperature,
                    is_day,
                    precipitation,
                    rain,
                    weather_code,
                    cloud_cover,
                    surface_pressure,
                    wind_speed,
                    wind_direction,
                    wind_gusts,
                    raw_data
                )
                VALUES (
                    :observed_at,
                    :provider,
                    :latitude,
                    :longitude,
                    :temperature,
                    :humidity,
                    :apparent_temperature,
                    :is_day,
                    :precipitation,
                    :rain,
                    :weather_code,
                    :cloud_cover,
                    :surface_pressure,
                    :wind_speed,
                    :wind_direction,
                    :wind_gusts,
                    CAST(:raw_data AS JSONB)
                )
                ON CONFLICT (
                    provider,
                    observed_at
                )
                DO UPDATE SET
                    fetched_at = NOW(),
                    latitude = EXCLUDED.latitude,
                    longitude = EXCLUDED.longitude,
                    temperature = EXCLUDED.temperature,
                    humidity = EXCLUDED.humidity,
                    apparent_temperature =
                        EXCLUDED.apparent_temperature,
                    is_day = EXCLUDED.is_day,
                    precipitation =
                        EXCLUDED.precipitation,
                    rain = EXCLUDED.rain,
                    weather_code =
                        EXCLUDED.weather_code,
                    cloud_cover =
                        EXCLUDED.cloud_cover,
                    surface_pressure =
                        EXCLUDED.surface_pressure,
                    wind_speed =
                        EXCLUDED.wind_speed,
                    wind_direction =
                        EXCLUDED.wind_direction,
                    wind_gusts =
                        EXCLUDED.wind_gusts,
                    raw_data =
                        EXCLUDED.raw_data
                """
            ),
            parameters,
        )

        self.store_normalized_current_measurements(
            connection=connection,
            observed_at=observed_at,
            current=current,
        )

        self.current_temperature = temperature
        self.current_humidity = humidity

    def store_normalized_current_measurements(
        self,
        connection: Any,
        observed_at: datetime,
        current: dict[str, Any],
    ) -> None:
        for source_metric, normalized_metric in (
            NORMALIZED_CURRENT_METRICS.items()
        ):
            value = safe_number(
                current.get(source_metric)
            )

            if value is None:
                continue

            connection.execute(
                text(
                    """
                    INSERT INTO sensor_measurements (
                        measured_at,
                        source,
                        sensor_name,
                        metric,
                        value,
                        unit,
                        quality,
                        mqtt_topic
                    )
                    SELECT
                        :measured_at,
                        :source,
                        'weather_outdoor',
                        :metric,
                        :value,
                        :unit,
                        'weather_model',
                        'weather/open-meteo/current'
                    WHERE NOT EXISTS (
                        SELECT 1
                        FROM sensor_measurements
                        WHERE measured_at = :measured_at
                          AND source = :source
                          AND sensor_name =
                              'weather_outdoor'
                          AND metric = :metric
                    )
                    """
                ),
                {
                    "measured_at": observed_at,
                    "source": WEATHER_PROVIDER,
                    "metric": normalized_metric,
                    "value": value,
                    "unit": UNITS.get(source_metric),
                },
            )

    def get_hourly_value(
        self,
        hourly: dict[str, Any],
        variable: str,
        index: int,
    ) -> Any:
        values = hourly.get(variable)

        if not isinstance(values, list):
            return None

        if index >= len(values):
            return None

        return values[index]

    def store_forecasts(
        self,
        connection: Any,
        payload: dict[str, Any],
    ) -> int:
        hourly = payload.get("hourly") or {}
        times = hourly.get("time") or []

        if not isinstance(times, list):
            raise RuntimeError(
                "Format des heures de prévision invalide"
            )

        stored_count = 0

        for index, time_value in enumerate(times):
            if not time_value:
                continue

            forecast_at = parse_datetime(time_value)

            raw_row = {
                variable: self.get_hourly_value(
                    hourly,
                    variable,
                    index,
                )
                for variable in HOURLY_VARIABLES
            }

            parameters = {
                "forecast_at": forecast_at,
                "provider": WEATHER_PROVIDER,
                "latitude": WEATHER_LATITUDE,
                "longitude": WEATHER_LONGITUDE,
                "temperature": safe_number(
                    raw_row.get("temperature_2m")
                ),
                "humidity": safe_number(
                    raw_row.get(
                        "relative_humidity_2m"
                    )
                ),
                "dew_point": safe_number(
                    raw_row.get("dew_point_2m")
                ),
                "apparent_temperature": safe_number(
                    raw_row.get(
                        "apparent_temperature"
                    )
                ),
                "precipitation_probability": safe_number(
                    raw_row.get(
                        "precipitation_probability"
                    )
                ),
                "precipitation": safe_number(
                    raw_row.get("precipitation")
                ),
                "rain": safe_number(
                    raw_row.get("rain")
                ),
                "weather_code": raw_row.get(
                    "weather_code"
                ),
                "cloud_cover": safe_number(
                    raw_row.get("cloud_cover")
                ),
                "visibility": safe_number(
                    raw_row.get("visibility")
                ),
                "surface_pressure": safe_number(
                    raw_row.get("surface_pressure")
                ),
                "wind_speed": safe_number(
                    raw_row.get("wind_speed_10m")
                ),
                "wind_direction": safe_number(
                    raw_row.get(
                        "wind_direction_10m"
                    )
                ),
                "wind_gusts": safe_number(
                    raw_row.get("wind_gusts_10m")
                ),
                "shortwave_radiation": safe_number(
                    raw_row.get(
                        "shortwave_radiation"
                    )
                ),
                "direct_radiation": safe_number(
                    raw_row.get("direct_radiation")
                ),
                "diffuse_radiation": safe_number(
                    raw_row.get(
                        "diffuse_radiation"
                    )
                ),
                "direct_normal_irradiance": safe_number(
                    raw_row.get(
                        "direct_normal_irradiance"
                    )
                ),
                "sunshine_duration": safe_number(
                    raw_row.get("sunshine_duration")
                ),
                "raw_data": json.dumps(
                    raw_row,
                    ensure_ascii=False,
                ),
            }

            connection.execute(
                text(
                    """
                    INSERT INTO weather_forecasts (
                        forecast_at,
                        provider,
                        latitude,
                        longitude,
                        temperature,
                        humidity,
                        dew_point,
                        apparent_temperature,
                        precipitation_probability,
                        precipitation,
                        rain,
                        weather_code,
                        cloud_cover,
                        visibility,
                        surface_pressure,
                        wind_speed,
                        wind_direction,
                        wind_gusts,
                        shortwave_radiation,
                        direct_radiation,
                        diffuse_radiation,
                        direct_normal_irradiance,
                        sunshine_duration,
                        raw_data
                    )
                    VALUES (
                        :forecast_at,
                        :provider,
                        :latitude,
                        :longitude,
                        :temperature,
                        :humidity,
                        :dew_point,
                        :apparent_temperature,
                        :precipitation_probability,
                        :precipitation,
                        :rain,
                        :weather_code,
                        :cloud_cover,
                        :visibility,
                        :surface_pressure,
                        :wind_speed,
                        :wind_direction,
                        :wind_gusts,
                        :shortwave_radiation,
                        :direct_radiation,
                        :diffuse_radiation,
                        :direct_normal_irradiance,
                        :sunshine_duration,
                        CAST(:raw_data AS JSONB)
                    )
                    ON CONFLICT (
                        provider,
                        forecast_at
                    )
                    DO UPDATE SET
                        fetched_at = NOW(),
                        latitude = EXCLUDED.latitude,
                        longitude = EXCLUDED.longitude,
                        temperature =
                            EXCLUDED.temperature,
                        humidity =
                            EXCLUDED.humidity,
                        dew_point =
                            EXCLUDED.dew_point,
                        apparent_temperature =
                            EXCLUDED.apparent_temperature,
                        precipitation_probability =
                            EXCLUDED.precipitation_probability,
                        precipitation =
                            EXCLUDED.precipitation,
                        rain = EXCLUDED.rain,
                        weather_code =
                            EXCLUDED.weather_code,
                        cloud_cover =
                            EXCLUDED.cloud_cover,
                        visibility =
                            EXCLUDED.visibility,
                        surface_pressure =
                            EXCLUDED.surface_pressure,
                        wind_speed =
                            EXCLUDED.wind_speed,
                        wind_direction =
                            EXCLUDED.wind_direction,
                        wind_gusts =
                            EXCLUDED.wind_gusts,
                        shortwave_radiation =
                            EXCLUDED.shortwave_radiation,
                        direct_radiation =
                            EXCLUDED.direct_radiation,
                        diffuse_radiation =
                            EXCLUDED.diffuse_radiation,
                        direct_normal_irradiance =
                            EXCLUDED.direct_normal_irradiance,
                        sunshine_duration =
                            EXCLUDED.sunshine_duration,
                        raw_data =
                            EXCLUDED.raw_data
                    """
                ),
                parameters,
            )

            stored_count += 1

        return stored_count

    def refresh(self) -> None:
        start_time = utc_now()
        self.last_attempt_at = start_time.isoformat()

        try:
            payload = self.fetch_weather()

            with self.engine.begin() as connection:
                self.store_current(
                    connection,
                    payload,
                )

                forecast_count = self.store_forecasts(
                    connection,
                    payload,
                )

                connection.execute(
                    text(
                        """
                        DELETE FROM weather_forecasts
                        WHERE forecast_at <
                            NOW() - INTERVAL '12 hours'
                        """
                    )
                )

                duration_ms = (
                    utc_now() - start_time
                ).total_seconds() * 1000

                connection.execute(
                    text(
                        """
                        INSERT INTO weather_fetch_history (
                            provider,
                            successful,
                            forecast_count,
                            duration_ms
                        )
                        VALUES (
                            :provider,
                            TRUE,
                            :forecast_count,
                            :duration_ms
                        )
                        """
                    ),
                    {
                        "provider": WEATHER_PROVIDER,
                        "forecast_count": forecast_count,
                        "duration_ms": duration_ms,
                    },
                )

            self.forecast_count = forecast_count
            self.refresh_count += 1
            self.last_success_at = utc_now().isoformat()
            self.last_error = None

            logger.info(
                "Météo actualisée : température=%s°C, "
                "humidité=%s%%, prévisions=%s",
                self.current_temperature,
                self.current_humidity,
                self.forecast_count,
            )

        except Exception as exc:
            self.last_error = str(exc)

            duration_ms = (
                utc_now() - start_time
            ).total_seconds() * 1000

            logger.exception(
                "Échec de l'actualisation météo"
            )

            try:
                with self.engine.begin() as connection:
                    connection.execute(
                        text(
                            """
                            INSERT INTO weather_fetch_history (
                                provider,
                                successful,
                                forecast_count,
                                duration_ms,
                                error_message
                            )
                            VALUES (
                                :provider,
                                FALSE,
                                0,
                                :duration_ms,
                                :error_message
                            )
                            """
                        ),
                        {
                            "provider": WEATHER_PROVIDER,
                            "duration_ms": duration_ms,
                            "error_message": str(exc),
                        },
                    )
            except Exception:
                logger.exception(
                    "Impossible de journaliser "
                    "l'erreur météo"
                )

            raise

    def start(self) -> None:
        self.initialize_database()
        self.running = True

        def worker() -> None:
            while not self.stop_event.is_set():
                try:
                    self.refresh()
                except Exception:
                    pass

                self.stop_event.wait(
                    WEATHER_REFRESH_SECONDS
                )

            self.running = False

        threading.Thread(
            target=worker,
            daemon=True,
            name="weather-worker",
        ).start()

    def stop(self) -> None:
        self.stop_event.set()
        self.running = False

    def status(self) -> dict[str, Any]:
        return {
            "running": self.running,
            "provider": WEATHER_PROVIDER,
            "latitude": WEATHER_LATITUDE,
            "longitude": WEATHER_LONGITUDE,
            "timezone": WEATHER_TIMEZONE,
            "refresh_seconds": WEATHER_REFRESH_SECONDS,
            "forecast_days": WEATHER_FORECAST_DAYS,
            "last_attempt_at": self.last_attempt_at,
            "last_success_at": self.last_success_at,
            "last_error": self.last_error,
            "refresh_count": self.refresh_count,
            "current_temperature":
                self.current_temperature,
            "current_humidity":
                self.current_humidity,
            "forecast_count":
                self.forecast_count,
        }
