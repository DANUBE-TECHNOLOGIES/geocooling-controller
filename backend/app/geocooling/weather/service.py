from __future__ import annotations

import asyncio
import json
import logging
import os
import threading
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any
from urllib.parse import urlencode
from urllib.request import Request, urlopen

LOGGER = logging.getLogger(__name__)

OPEN_METEO_FORECAST_URL = "https://api.open-meteo.com/v1/forecast"
OPEN_METEO_GEOCODING_URL = "https://geocoding-api.open-meteo.com/v1/search"

DEFAULT_LOCATION = "Chevannes"
DEFAULT_POSTAL_CODE = "45210"
DEFAULT_COUNTRY_CODE = "FR"
DEFAULT_TIMEZONE = "Europe/Paris"

CURRENT_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "dew_point_2m",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
)

HOURLY_VARIABLES = (
    "temperature_2m",
    "relative_humidity_2m",
    "apparent_temperature",
    "dew_point_2m",
    "precipitation_probability",
    "precipitation",
    "rain",
    "weather_code",
    "cloud_cover",
    "pressure_msl",
    "wind_speed_10m",
    "wind_direction_10m",
    "wind_gusts_10m",
    "shortwave_radiation",
    "direct_radiation",
    "diffuse_radiation",
)

DAILY_VARIABLES = (
    "weather_code",
    "temperature_2m_max",
    "temperature_2m_min",
    "apparent_temperature_max",
    "apparent_temperature_min",
    "sunrise",
    "sunset",
    "daylight_duration",
    "sunshine_duration",
    "precipitation_sum",
    "rain_sum",
    "precipitation_probability_max",
    "wind_speed_10m_max",
    "wind_gusts_10m_max",
)


@dataclass(frozen=True)
class WeatherLocation:
    latitude: float
    longitude: float
    name: str
    postal_code: str | None
    country: str | None
    timezone: str


@dataclass
class CacheEntry:
    created_monotonic: float
    payload: dict[str, Any]


class WeatherConfigurationError(RuntimeError):
    """Configuration météo invalide ou incomplète."""


class WeatherProviderError(RuntimeError):
    """Erreur de communication ou de format du fournisseur météo."""


class WeatherService:
    """
    Service météo Open-Meteo avec cache mémoire.

    Le service ne pilote jamais le matériel. Il expose uniquement des
    observations et des prévisions utilisables ultérieurement par le Brain.
    """

    def __init__(self) -> None:
        self._timeout_seconds = self._read_float(
            "GEOCOOLING_WEATHER_TIMEOUT_SECONDS",
            12.0,
            minimum=2.0,
            maximum=60.0,
        )

        self._cache_seconds = self._read_float(
            "GEOCOOLING_WEATHER_CACHE_SECONDS",
            900.0,
            minimum=30.0,
            maximum=3600.0,
        )

        self._forecast_hours = self._read_int(
            "GEOCOOLING_WEATHER_FORECAST_HOURS",
            48,
            minimum=6,
            maximum=168,
        )

        self._forecast_days = self._read_int(
            "GEOCOOLING_WEATHER_FORECAST_DAYS",
            7,
            minimum=1,
            maximum=16,
        )

        self._timezone = (
            os.getenv("GEOCOOLING_WEATHER_TIMEZONE", DEFAULT_TIMEZONE).strip()
            or DEFAULT_TIMEZONE
        )

        self._lock = threading.RLock()
        self._weather_cache: CacheEntry | None = None
        self._location_cache: WeatherLocation | None = None

    @staticmethod
    def _read_float(
        name: str,
        default: float,
        *,
        minimum: float,
        maximum: float,
    ) -> float:
        raw = os.getenv(name)

        if raw is None or not raw.strip():
            return default

        try:
            value = float(raw)
        except ValueError as exc:
            raise WeatherConfigurationError(
                f"{name} doit être un nombre, valeur reçue : {raw!r}"
            ) from exc

        if value < minimum or value > maximum:
            raise WeatherConfigurationError(
                f"{name} doit être compris entre {minimum} et {maximum}"
            )

        return value

    @staticmethod
    def _read_int(
        name: str,
        default: int,
        *,
        minimum: int,
        maximum: int,
    ) -> int:
        raw = os.getenv(name)

        if raw is None or not raw.strip():
            return default

        try:
            value = int(raw)
        except ValueError as exc:
            raise WeatherConfigurationError(
                f"{name} doit être un entier, valeur reçue : {raw!r}"
            ) from exc

        if value < minimum or value > maximum:
            raise WeatherConfigurationError(
                f"{name} doit être compris entre {minimum} et {maximum}"
            )

        return value

    @staticmethod
    def _optional_coordinate(name: str) -> float | None:
        raw = os.getenv(name)

        if raw is None or not raw.strip():
            return None

        try:
            return float(raw)
        except ValueError as exc:
            raise WeatherConfigurationError(
                f"{name} doit être une coordonnée numérique"
            ) from exc

    def _request_json(
        self,
        base_url: str,
        parameters: dict[str, Any],
    ) -> dict[str, Any]:
        query = urlencode(parameters, doseq=True)
        url = f"{base_url}?{query}"

        request = Request(
            url,
            headers={
                "Accept": "application/json",
                "User-Agent": "GeoCooling-Controller/1.0",
            },
            method="GET",
        )

        try:
            with urlopen(request, timeout=self._timeout_seconds) as response:
                status = getattr(response, "status", 200)
                body = response.read().decode("utf-8")
        except Exception as exc:
            raise WeatherProviderError(
                f"Impossible de contacter Open-Meteo : {exc}"
            ) from exc

        if status < 200 or status >= 300:
            raise WeatherProviderError(
                f"Open-Meteo a répondu avec le statut HTTP {status}"
            )

        try:
            payload = json.loads(body)
        except json.JSONDecodeError as exc:
            raise WeatherProviderError(
                "Réponse JSON Open-Meteo invalide"
            ) from exc

        if not isinstance(payload, dict):
            raise WeatherProviderError(
                "Format de réponse Open-Meteo inattendu"
            )

        if payload.get("error"):
            raise WeatherProviderError(
                str(payload.get("reason") or "Erreur Open-Meteo")
            )

        return payload

    def _resolve_location_sync(self) -> WeatherLocation:
        with self._lock:
            if self._location_cache is not None:
                return self._location_cache

        latitude = self._optional_coordinate(
            "GEOCOOLING_WEATHER_LATITUDE"
        )
        longitude = self._optional_coordinate(
            "GEOCOOLING_WEATHER_LONGITUDE"
        )

        configured_name = (
            os.getenv("GEOCOOLING_WEATHER_LOCATION", DEFAULT_LOCATION).strip()
            or DEFAULT_LOCATION
        )

        configured_postal_code = (
            os.getenv(
                "GEOCOOLING_WEATHER_POSTAL_CODE",
                DEFAULT_POSTAL_CODE,
            ).strip()
            or DEFAULT_POSTAL_CODE
        )

        configured_country_code = (
            os.getenv(
                "GEOCOOLING_WEATHER_COUNTRY_CODE",
                DEFAULT_COUNTRY_CODE,
            ).strip()
            or DEFAULT_COUNTRY_CODE
        ).upper()

        if latitude is not None or longitude is not None:
            if latitude is None or longitude is None:
                raise WeatherConfigurationError(
                    "Latitude et longitude doivent être renseignées ensemble"
                )

            location = WeatherLocation(
                latitude=latitude,
                longitude=longitude,
                name=configured_name,
                postal_code=configured_postal_code,
                country=configured_country_code,
                timezone=self._timezone,
            )

            with self._lock:
                self._location_cache = location

            return location

        search_terms = [
            configured_postal_code,
            configured_name,
        ]

        results: list[Any] = []
        successful_search_term: str | None = None

        for search_term in search_terms:
            if not search_term:
                continue

            try:
                payload = self._request_json(
                    OPEN_METEO_GEOCODING_URL,
                    {
                        "name": search_term,
                        "count": 100,
                        "language": "fr",
                        "format": "json",
                        "countryCode": configured_country_code,
                    },
                )
            except WeatherProviderError:
                LOGGER.warning(
                    "Échec du géocodage Open-Meteo pour %s",
                    search_term,
                )
                continue

            candidate_results = payload.get("results")

            if isinstance(candidate_results, list) and candidate_results:
                results = candidate_results
                successful_search_term = search_term
                break

        if not results:
            raise WeatherConfigurationError(
                "Localité météo introuvable avec les recherches "
                f"{search_terms!r}. Configurez explicitement "
                "GEOCOOLING_WEATHER_LATITUDE et "
                "GEOCOOLING_WEATHER_LONGITUDE."
            )

        LOGGER.info(
            "Géocodage météo résolu avec le terme %s",
            successful_search_term,
        )

        selected: dict[str, Any] | None = None

        for candidate in results:
            if not isinstance(candidate, dict):
                continue

            candidate_postal_codes = candidate.get("postcodes") or []
            candidate_country_code = str(
                candidate.get("country_code") or ""
            ).upper()

            if (
                configured_postal_code in candidate_postal_codes
                and candidate_country_code == configured_country_code
            ):
                selected = candidate
                break

        if selected is None:
            for candidate in results:
                if not isinstance(candidate, dict):
                    continue

                if (
                    str(candidate.get("country_code") or "").upper()
                    == configured_country_code
                ):
                    selected = candidate
                    break

        if selected is None:
            selected = results[0]

        try:
            resolved_latitude = float(selected["latitude"])
            resolved_longitude = float(selected["longitude"])
        except (KeyError, TypeError, ValueError) as exc:
            raise WeatherProviderError(
                "Coordonnées absentes de la réponse de géocodage"
            ) from exc

        location = WeatherLocation(
            latitude=resolved_latitude,
            longitude=resolved_longitude,
            name=str(selected.get("name") or configured_name),
            postal_code=configured_postal_code,
            country=str(
                selected.get("country") or configured_country_code
            ),
            timezone=str(selected.get("timezone") or self._timezone),
        )

        with self._lock:
            self._location_cache = location

        return location

    @staticmethod
    def _hourly_rows(
        hourly: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(hourly, dict):
            return []

        times = hourly.get("time")

        if not isinstance(times, list):
            return []

        variables = {
            key: value
            for key, value in hourly.items()
            if key != "time" and isinstance(value, list)
        }

        rows: list[dict[str, Any]] = []

        for index, timestamp in enumerate(times):
            row: dict[str, Any] = {"time": timestamp}

            for variable, values in variables.items():
                row[variable] = (
                    values[index] if index < len(values) else None
                )

            rows.append(row)

        return rows

    @staticmethod
    def _daily_rows(
        daily: Any,
    ) -> list[dict[str, Any]]:
        if not isinstance(daily, dict):
            return []

        times = daily.get("time")

        if not isinstance(times, list):
            return []

        variables = {
            key: value
            for key, value in daily.items()
            if key != "time" and isinstance(value, list)
        }

        rows: list[dict[str, Any]] = []

        for index, date in enumerate(times):
            row: dict[str, Any] = {"date": date}

            for variable, values in variables.items():
                row[variable] = (
                    values[index] if index < len(values) else None
                )

            rows.append(row)

        return rows

    @staticmethod
    def _derive_summary(
        hourly_rows: list[dict[str, Any]],
    ) -> dict[str, Any]:
        first_24_hours = hourly_rows[:24]

        temperatures = [
            row.get("temperature_2m")
            for row in first_24_hours
            if isinstance(row.get("temperature_2m"), (int, float))
        ]

        humidities = [
            row.get("relative_humidity_2m")
            for row in first_24_hours
            if isinstance(row.get("relative_humidity_2m"), (int, float))
        ]

        solar_values = [
            row.get("shortwave_radiation")
            for row in first_24_hours
            if isinstance(row.get("shortwave_radiation"), (int, float))
        ]

        precipitation_probabilities = [
            row.get("precipitation_probability")
            for row in first_24_hours
            if isinstance(
                row.get("precipitation_probability"),
                (int, float),
            )
        ]

        return {
            "horizon_hours": len(first_24_hours),
            "temperature_min_24h": (
                min(temperatures) if temperatures else None
            ),
            "temperature_max_24h": (
                max(temperatures) if temperatures else None
            ),
            "temperature_average_24h": (
                sum(temperatures) / len(temperatures)
                if temperatures
                else None
            ),
            "humidity_average_24h": (
                sum(humidities) / len(humidities)
                if humidities
                else None
            ),
            "solar_radiation_peak_24h": (
                max(solar_values) if solar_values else None
            ),
            "precipitation_probability_max_24h": (
                max(precipitation_probabilities)
                if precipitation_probabilities
                else None
            ),
        }

    def _fetch_weather_sync(self) -> dict[str, Any]:
        location = self._resolve_location_sync()

        payload = self._request_json(
            OPEN_METEO_FORECAST_URL,
            {
                "latitude": location.latitude,
                "longitude": location.longitude,
                "timezone": location.timezone,
                "current": ",".join(CURRENT_VARIABLES),
                "hourly": ",".join(HOURLY_VARIABLES),
                "daily": ",".join(DAILY_VARIABLES),
                "forecast_hours": self._forecast_hours,
                "forecast_days": self._forecast_days,
                "temperature_unit": "celsius",
                "wind_speed_unit": "kmh",
                "precipitation_unit": "mm",
            },
        )

        hourly_rows = self._hourly_rows(payload.get("hourly"))
        daily_rows = self._daily_rows(payload.get("daily"))

        normalized = {
            "provider": "open-meteo",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "location": {
                "name": location.name,
                "postal_code": location.postal_code,
                "country": location.country,
                "latitude": location.latitude,
                "longitude": location.longitude,
                "elevation": payload.get("elevation"),
                "timezone": payload.get("timezone") or location.timezone,
                "utc_offset_seconds": payload.get("utc_offset_seconds"),
            },
            "current": payload.get("current") or {},
            "current_units": payload.get("current_units") or {},
            "hourly": hourly_rows,
            "hourly_units": payload.get("hourly_units") or {},
            "daily": daily_rows,
            "daily_units": payload.get("daily_units") or {},
            "summary": self._derive_summary(hourly_rows),
            "forecast_hours": len(hourly_rows),
            "forecast_days": len(daily_rows),
            "cache": {
                "ttl_seconds": self._cache_seconds,
                "from_cache": False,
                "age_seconds": 0,
            },
        }

        return normalized

    def get_weather_sync(
        self,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        now = time.monotonic()

        with self._lock:
            cached = self._weather_cache

            if cached is not None and not force_refresh:
                age = now - cached.created_monotonic

                if age < self._cache_seconds:
                    payload = dict(cached.payload)
                    payload["cache"] = {
                        "ttl_seconds": self._cache_seconds,
                        "from_cache": True,
                        "age_seconds": round(age, 3),
                    }
                    return payload

        payload = self._fetch_weather_sync()

        with self._lock:
            self._weather_cache = CacheEntry(
                created_monotonic=time.monotonic(),
                payload=payload,
            )

        return payload

    async def get_weather(
        self,
        *,
        force_refresh: bool = False,
    ) -> dict[str, Any]:
        return await asyncio.to_thread(
            self.get_weather_sync,
            force_refresh=force_refresh,
        )

    def health(self) -> dict[str, Any]:
        with self._lock:
            cache = self._weather_cache
            location = self._location_cache

        cache_age = (
            time.monotonic() - cache.created_monotonic
            if cache is not None
            else None
        )

        return {
            "service": "weather-intelligence",
            "provider": "open-meteo",
            "configured": True,
            "read_only": True,
            "brain_connected": False,
            "cache": {
                "available": cache is not None,
                "age_seconds": (
                    round(cache_age, 3)
                    if cache_age is not None
                    else None
                ),
                "ttl_seconds": self._cache_seconds,
            },
            "location": (
                {
                    "name": location.name,
                    "postal_code": location.postal_code,
                    "country": location.country,
                    "latitude": location.latitude,
                    "longitude": location.longitude,
                    "timezone": location.timezone,
                }
                if location is not None
                else None
            ),
            "forecast_hours": self._forecast_hours,
            "forecast_days": self._forecast_days,
        }


weather_service = WeatherService()
