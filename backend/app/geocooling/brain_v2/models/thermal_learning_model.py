from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any


@dataclass(slots=True)
class LearnedMetric:
    value: float | None = None
    unit: str = ""
    sample_count: int = 0
    confidence_percent: float = 0.0
    minimum: float | None = None
    maximum: float | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(slots=True)
class ThermalLearningModel:
    version: str = "C022.2-THERMAL-LEARNING-1.0"
    status: str = "COLLECTING"
    generated_at: str = field(
        default_factory=lambda: datetime.now(
            timezone.utc
        ).isoformat()
    )

    source_observations: int = 0
    valid_observations: int = 0
    rejected_observations: int = 0
    usable_transitions: int = 0
    active_cooling_transitions: int = 0
    passive_transitions: int = 0

    observation_start: str | None = None
    observation_end: str | None = None
    observation_duration_hours: float = 0.0

    building_cooling_rate: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="°C/h"
        )
    )

    building_passive_warming_rate: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="°C/h"
        )
    )

    floor_supply_return_delta: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="°C"
        )
    )

    floor_surface_supply_delta: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="°C"
        )
    )

    hydraulic_power: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="kW"
        )
    )

    source_exchange_power: LearnedMetric = field(
        default_factory=lambda: LearnedMetric(
            unit="kW"
        )
    )

    global_confidence_percent: float = 0.0
    learning_state: str = "COLLECTING"
    recommendations: list[str] = field(
        default_factory=list
    )
    safety: dict[str, Any] = field(
        default_factory=lambda: {
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
        }
    )

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)

        payload["building_cooling_rate"] = (
            self.building_cooling_rate.to_dict()
        )
        payload["building_passive_warming_rate"] = (
            self.building_passive_warming_rate.to_dict()
        )
        payload["floor_supply_return_delta"] = (
            self.floor_supply_return_delta.to_dict()
        )
        payload["floor_surface_supply_delta"] = (
            self.floor_surface_supply_delta.to_dict()
        )
        payload["hydraulic_power"] = (
            self.hydraulic_power.to_dict()
        )
        payload["source_exchange_power"] = (
            self.source_exchange_power.to_dict()
        )

        return payload
