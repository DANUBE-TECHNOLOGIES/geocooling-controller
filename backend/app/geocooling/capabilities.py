from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping


NumberParser = Callable[[Any], float | None]


@dataclass(frozen=True, slots=True)
class BuildingCapabilities:
    indoor_temperature: bool
    indoor_humidity: bool
    outdoor_temperature: bool

    @property
    def available_count(self) -> int:
        return sum(
            (
                self.indoor_temperature,
                self.indoor_humidity,
                self.outdoor_temperature,
            )
        )

    @property
    def total_count(self) -> int:
        return 3

    @property
    def complete(self) -> bool:
        return self.available_count == self.total_count


@dataclass(frozen=True, slots=True)
class HydraulicCapabilities:
    surface_temperature: bool
    floor_supply_temperature: bool
    floor_return_temperature: bool
    source_inlet_temperature: bool
    source_outlet_temperature: bool
    flow_meter: bool

    @property
    def available_count(self) -> int:
        return sum(
            (
                self.surface_temperature,
                self.floor_supply_temperature,
                self.floor_return_temperature,
                self.source_inlet_temperature,
                self.source_outlet_temperature,
                self.flow_meter,
            )
        )

    @property
    def total_count(self) -> int:
        return 6

    @property
    def sufficient_for_full_mode(self) -> bool:
        return self.available_count >= 4


@dataclass(frozen=True, slots=True)
class GeoCoolingCapabilities:
    building: BuildingCapabilities
    hydraulic: HydraulicCapabilities

    @classmethod
    def from_latest(
        cls,
        latest: Mapping[str, Any],
        *,
        number_parser: NumberParser,
    ) -> "GeoCoolingCapabilities":
        def available(field_name: str) -> bool:
            return number_parser(latest.get(field_name)) is not None

        return cls(
            building=BuildingCapabilities(
                indoor_temperature=available(
                    "indoor_temperature_c"
                ),
                indoor_humidity=available(
                    "indoor_humidity_percent"
                ),
                outdoor_temperature=available(
                    "outdoor_temperature_c"
                ),
            ),
            hydraulic=HydraulicCapabilities(
                surface_temperature=available(
                    "surface_temperature_c"
                ),
                floor_supply_temperature=available(
                    "floor_supply_temperature_c"
                ),
                floor_return_temperature=available(
                    "floor_return_temperature_c"
                ),
                source_inlet_temperature=available(
                    "source_inlet_temperature_c"
                ),
                source_outlet_temperature=available(
                    "source_outlet_temperature_c"
                ),
                flow_meter=available(
                    "flow_rate_l_min"
                ),
            ),
        )

    @property
    def data_quality(self) -> float:
        building_score = (
            self.building.available_count
            / self.building.total_count
            * 70.0
        )

        hydraulic_score = (
            self.hydraulic.available_count
            / self.hydraulic.total_count
            * 30.0
        )

        return max(
            0.0,
            min(
                100.0,
                building_score + hydraulic_score,
            ),
        )

    @property
    def operating_mode(self) -> str:
        if (
            self.building.complete
            and self.hydraulic.sufficient_for_full_mode
        ):
            return "FULL"

        if self.building.complete:
            return "BUILDING_ONLY"

        if self.building.available_count >= 2:
            return "LIMITED"

        return "INSUFFICIENT_DATA"

    def as_dict(self) -> dict[str, Any]:
        return {
            "building": asdict(self.building),
            "hydraulic": asdict(self.hydraulic),
            "summary": {
                "building_available": (
                    self.building.available_count
                ),
                "building_total": (
                    self.building.total_count
                ),
                "hydraulic_available": (
                    self.hydraulic.available_count
                ),
                "hydraulic_total": (
                    self.hydraulic.total_count
                ),
                "data_quality": self.data_quality,
                "operating_mode": self.operating_mode,
            },
        }
