"""
RC3.5 — Weather/Inertia multi-horizon thermal predictor.

Passive, read-only model:
- consumes current Decision Context and weather payloads;
- predicts indoor temperature from 30 minutes to 48 hours;
- simulates BASELINE, SOFT_COOLING and FULL_COOLING trajectories;
- never calls the Controller or hardware.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import exp, isfinite
from typing import Any, Iterable, Mapping, Sequence


@dataclass(frozen=True, slots=True)
class WeatherPoint:
    horizon_minutes: int
    outdoor_temperature_c: float
    cloud_cover_pct: float | None = None
    solar_radiation_w_m2: float | None = None
    relative_humidity_pct: float | None = None


@dataclass(frozen=True, slots=True)
class ThermalModelParameters:
    fast_time_constant_hours: float = 2.5
    slow_time_constant_hours: float = 18.0
    mass_coupling: float = 0.28
    solar_gain_c_per_hour_at_full_sun: float = 0.20
    soft_cooling_c_per_hour: float = 0.28
    full_cooling_c_per_hour: float = 0.52
    model_confidence: float = 0.62


@dataclass(frozen=True, slots=True)
class TrajectoryPoint:
    horizon_minutes: int
    predicted_indoor_temperature_c: float
    predicted_mass_temperature_c: float
    outdoor_temperature_c: float
    cloud_cover_pct: float | None
    solar_gain_c_per_hour: float
    cooling_gain_c_per_hour: float
    confidence: float
    uncertainty_c: float


@dataclass(frozen=True, slots=True)
class ThermalTrajectory:
    scenario: str
    points: tuple[TrajectoryPoint, ...]

    def as_dict(self) -> dict[str, Any]:
        return {
            "scenario": self.scenario,
            "points": [asdict(point) for point in self.points],
        }


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if isfinite(result) else None


def _walk(node: Any) -> Iterable[tuple[str, Any]]:
    if isinstance(node, Mapping):
        for key, value in node.items():
            yield str(key), value
            yield from _walk(value)
    elif isinstance(node, Sequence) and not isinstance(
        node, (str, bytes, bytearray)
    ):
        for item in node:
            yield from _walk(item)


def _first(payload: Mapping[str, Any] | None, names: Sequence[str]) -> Any:
    if not isinstance(payload, Mapping):
        return None

    wanted = {name.lower() for name in names}

    for key, value in _walk(payload):
        if key.lower() in wanted and value is not None:
            return value

    return None


def _context_value(
    context: Mapping[str, Any],
    section: str,
    name: str,
) -> float | None:
    section_value = context.get(section)

    if not isinstance(section_value, Mapping):
        return None

    return _number(section_value.get(name))


def _extract_hourly_arrays(
    weather: Mapping[str, Any],
) -> tuple[list[Any], list[Any], list[Any], list[Any]]:
    hourly = weather.get("hourly")

    if not isinstance(hourly, Mapping):
        hourly = weather.get("hourly_forecast")

    if not isinstance(hourly, Mapping):
        hourly = weather.get("forecast_hourly")

    if not isinstance(hourly, Mapping):
        return [], [], [], []

    times = list(
        hourly.get("time")
        or hourly.get("timestamps")
        or hourly.get("datetime")
        or []
    )
    temperatures = list(
        hourly.get("temperature_2m")
        or hourly.get("temperature")
        or hourly.get("temperatures")
        or []
    )
    clouds = list(
        hourly.get("cloud_cover")
        or hourly.get("cloudcover")
        or hourly.get("clouds")
        or []
    )
    solar = list(
        hourly.get("shortwave_radiation")
        or hourly.get("solar_radiation")
        or hourly.get("global_tilted_irradiance")
        or []
    )

    return times, temperatures, clouds, solar


def extract_weather_points(
    weather: Mapping[str, Any],
    *,
    fallback_outdoor_c: float,
    max_hours: int = 48,
) -> tuple[WeatherPoint, ...]:
    _, temperatures, clouds, solar = _extract_hourly_arrays(weather)
    points: list[WeatherPoint] = []

    if temperatures:
        length = min(max_hours + 1, len(temperatures))

        for index in range(length):
            temperature = _number(temperatures[index])

            if temperature is None:
                continue

            cloud = (
                _number(clouds[index])
                if index < len(clouds)
                else None
            )
            radiation = (
                _number(solar[index])
                if index < len(solar)
                else None
            )

            points.append(
                WeatherPoint(
                    horizon_minutes=index * 60,
                    outdoor_temperature_c=temperature,
                    cloud_cover_pct=cloud,
                    solar_radiation_w_m2=radiation,
                )
            )

    if not points:
        current = _number(
            _first(
                weather,
                (
                    "temperature_2m",
                    "outdoor_temperature",
                    "outdoor_temperature_c",
                    "temperature",
                ),
            )
        )

        outside = current if current is not None else fallback_outdoor_c

        points = [
            WeatherPoint(
                horizon_minutes=hour * 60,
                outdoor_temperature_c=outside,
            )
            for hour in range(max_hours + 1)
        ]

    return tuple(points)


class WeatherInertiaPredictor:
    HORIZONS_MINUTES = (
        30,
        60,
        120,
        240,
        360,
        720,
        1440,
        2880,
    )

    def __init__(
        self,
        parameters: ThermalModelParameters | None = None,
    ) -> None:
        self.parameters = parameters or ThermalModelParameters()

    def predict(
        self,
        *,
        context: Mapping[str, Any],
        weather: Mapping[str, Any],
    ) -> dict[str, Any]:
        indoor = _context_value(
            context,
            "measurements",
            "indoor_temperature_c",
        )
        outdoor = _context_value(
            context,
            "measurements",
            "outdoor_temperature_c",
        )
        floor_surface = _context_value(
            context,
            "measurements",
            "floor_surface_temperature_c",
        )

        if indoor is None:
            raise ValueError("indoor_temperature_c is required")

        if outdoor is None:
            outdoor = _number(
                _first(
                    weather,
                    (
                        "temperature_2m",
                        "outdoor_temperature",
                        "outdoor_temperature_c",
                        "temperature",
                    ),
                )
            )

        if outdoor is None:
            outdoor = indoor

        mass_temperature = (
            floor_surface
            if floor_surface is not None
            else indoor
        )

        weather_points = extract_weather_points(
            weather,
            fallback_outdoor_c=outdoor,
        )

        trajectories = tuple(
            self._simulate(
                scenario=scenario,
                indoor_c=indoor,
                mass_c=mass_temperature,
                weather_points=weather_points,
            )
            for scenario in (
                "BASELINE",
                "SOFT_COOLING",
                "FULL_COOLING",
            )
        )

        return {
            "schema": "geocooling.rc35.weather-inertia-prediction.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "SHADOW",
            "horizons_minutes": list(self.HORIZONS_MINUTES),
            "model": asdict(self.parameters),
            "input": {
                "indoor_temperature_c": indoor,
                "outdoor_temperature_c": outdoor,
                "mass_temperature_c": mass_temperature,
                "weather_points": len(weather_points),
            },
            "trajectories": [
                trajectory.as_dict()
                for trajectory in trajectories
            ],
            "safety": {
                "controller_authorized": False,
                "controller_called": False,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }

    def _simulate(
        self,
        *,
        scenario: str,
        indoor_c: float,
        mass_c: float,
        weather_points: tuple[WeatherPoint, ...],
    ) -> ThermalTrajectory:
        parameters = self.parameters
        air = indoor_c
        mass = mass_c
        points: list[TrajectoryPoint] = []

        weather_by_hour = {
            point.horizon_minutes // 60: point
            for point in weather_points
        }

        # 30-minute integration step to preserve short-horizon behaviour.
        for step in range(1, 97):
            horizon_minutes = step * 30
            hour = min(48, horizon_minutes // 60)
            weather_point = (
                weather_by_hour.get(hour)
                or weather_by_hour.get(hour - 1)
                or weather_points[-1]
            )

            dt_hours = 0.5
            outside = weather_point.outdoor_temperature_c

            fast_alpha = 1.0 - exp(
                -dt_hours / max(
                    0.1,
                    parameters.fast_time_constant_hours,
                )
            )
            slow_alpha = 1.0 - exp(
                -dt_hours / max(
                    0.1,
                    parameters.slow_time_constant_hours,
                )
            )

            cloud_factor = (
                1.0
                - max(
                    0.0,
                    min(
                        100.0,
                        weather_point.cloud_cover_pct,
                    ),
                )
                / 100.0
                if weather_point.cloud_cover_pct is not None
                else 0.5
            )
            radiation_factor = (
                max(
                    0.0,
                    min(
                        1.0,
                        weather_point.solar_radiation_w_m2 / 800.0,
                    ),
                )
                if weather_point.solar_radiation_w_m2 is not None
                else cloud_factor
            )
            solar_gain = (
                parameters.solar_gain_c_per_hour_at_full_sun
                * radiation_factor
            )

            cooling_gain = {
                "BASELINE": 0.0,
                "SOFT_COOLING": parameters.soft_cooling_c_per_hour,
                "FULL_COOLING": parameters.full_cooling_c_per_hour,
            }[scenario]

            # Slow thermal mass follows outside and exchanges with room air.
            mass += slow_alpha * (
                (outside - mass) * 0.55
                + (air - mass) * parameters.mass_coupling
            )

            # Fast air node reacts to outside, mass, solar gains and cooling.
            air += fast_alpha * (
                (outside - air) * 0.35
                + (mass - air) * parameters.mass_coupling
            )
            air += (solar_gain - cooling_gain) * dt_hours

            if horizon_minutes in self.HORIZONS_MINUTES:
                horizon_factor = horizon_minutes / 2880.0
                confidence = max(
                    0.20,
                    parameters.model_confidence
                    * (1.0 - 0.52 * horizon_factor),
                )
                uncertainty = (
                    0.18
                    + 1.45 * horizon_factor
                    + (1.0 - confidence) * 0.35
                )

                points.append(
                    TrajectoryPoint(
                        horizon_minutes=horizon_minutes,
                        predicted_indoor_temperature_c=round(air, 3),
                        predicted_mass_temperature_c=round(mass, 3),
                        outdoor_temperature_c=round(outside, 3),
                        cloud_cover_pct=weather_point.cloud_cover_pct,
                        solar_gain_c_per_hour=round(solar_gain, 4),
                        cooling_gain_c_per_hour=round(cooling_gain, 4),
                        confidence=round(confidence, 3),
                        uncertainty_c=round(uncertainty, 3),
                    )
                )

        return ThermalTrajectory(
            scenario=scenario,
            points=tuple(points),
        )
