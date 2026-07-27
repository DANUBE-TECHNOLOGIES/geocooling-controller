from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class MeasurementState:
    value: float | None = None
    unit: str | None = None
    measured_at: str | None = None
    age_seconds: int | None = None
    quality: str = "missing"
    source: str | None = None
    mqtt_topic: str | None = None
    fresh: bool = False


@dataclass(slots=True)
class ZoneState:
    name: str
    temperature: MeasurementState = field(default_factory=MeasurementState)
    humidity: MeasurementState = field(default_factory=MeasurementState)
    battery: MeasurementState = field(default_factory=MeasurementState)
    linkquality: MeasurementState = field(default_factory=MeasurementState)
    dew_point: float | None = None
    comfort_temperature: float | None = None
    available: bool = False


@dataclass(slots=True)
class WeatherState:
    temperature: MeasurementState = field(default_factory=MeasurementState)
    apparent_temperature: MeasurementState = field(default_factory=MeasurementState)
    humidity: MeasurementState = field(default_factory=MeasurementState)
    cloud_cover: MeasurementState = field(default_factory=MeasurementState)
    precipitation: MeasurementState = field(default_factory=MeasurementState)
    pressure: MeasurementState = field(default_factory=MeasurementState)
    wind_speed: MeasurementState = field(default_factory=MeasurementState)
    wind_gusts: MeasurementState = field(default_factory=MeasurementState)
    weather_code: MeasurementState = field(default_factory=MeasurementState)
    available: bool = False


@dataclass(slots=True)
class ThermalState:
    indoor_temperature: float | None = None
    indoor_humidity: float | None = None
    outdoor_temperature: float | None = None
    indoor_outdoor_delta: float | None = None
    dew_point: float | None = None
    slope_1h: float | None = None
    slope_3h: float | None = None
    data_quality: str = "missing"
    learning_ready: bool = False
    calculated_at: str | None = None


@dataclass(slots=True)
class GeoCoolingTwinState:
    state: str = "UNKNOWN"
    mode: str = "UNKNOWN"
    valve_open: bool = False
    pump_running: bool = False
    runtime_seconds: int = 0
    simulation: bool = True
    event_type: str | None = None
    reason: str | None = None
    updated_at: str | None = None


@dataclass(slots=True)
class LearningState:
    status: str = "collecting"
    parameters: dict[str, dict[str, Any]] = field(default_factory=dict)
    sample_count: int = 0
    ready: bool = False


@dataclass(slots=True)
class BuildingState:
    generated_at: str = field(default_factory=lambda: utc_now().isoformat())
    sequence: int = 0
    status: str = "initializing"
    data_quality: str = "missing"
    inside: dict[str, ZoneState] = field(default_factory=dict)
    outside: WeatherState = field(default_factory=WeatherState)
    thermal: ThermalState = field(default_factory=ThermalState)
    geocooling: GeoCoolingTwinState = field(default_factory=GeoCoolingTwinState)
    learning: LearningState = field(default_factory=LearningState)
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)
