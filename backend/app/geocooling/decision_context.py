from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Callable, Mapping


NumberParser = Callable[[Any], float | None]


@dataclass(frozen=True, slots=True)
class GeoCoolingDecisionContext:
    state: str

    indoor_temperature_c: float | None
    cooling_power_kw: float | None

    thermal_available: bool
    safety_safe: bool
    device_ready: bool

    remaining_minimum_off_seconds: int
    remaining_minimum_on_seconds: int

    predicted_temperature_1h_c: float | None
    predicted_temperature_3h_c: float | None
    predicted_temperature_6h_c: float | None

    @classmethod
    def build(
        cls,
        *,
        state: str,
        latest: Mapping[str, Any],
        thermal: Mapping[str, Any],
        safety: Mapping[str, Any],
        device: Mapping[str, Any],
        anti_short_cycle: Mapping[str, Any],
        prediction_by_horizon: Mapping[int, Any],
        number_parser: NumberParser,
    ) -> "GeoCoolingDecisionContext":
        def number(value: Any) -> float | None:
            return number_parser(value)

        def seconds(value: Any) -> int:
            parsed = number(value)

            if parsed is None:
                return 0

            return max(0, int(parsed))

        return cls(
            state=str(state or "").upper(),

            indoor_temperature_c=number(
                latest.get("indoor_temperature_c")
            ),
            cooling_power_kw=number(
                thermal.get("cooling_power_kw")
            ),

            thermal_available=bool(
                thermal.get("available", False)
            ),
            safety_safe=bool(
                safety.get("safe", False)
            ),
            device_ready=bool(
                device.get("ready", False)
            ),

            remaining_minimum_off_seconds=seconds(
                anti_short_cycle.get(
                    "remaining_minimum_off_seconds"
                )
            ),
            remaining_minimum_on_seconds=seconds(
                anti_short_cycle.get(
                    "remaining_minimum_on_seconds"
                )
            ),

            predicted_temperature_1h_c=number(
                prediction_by_horizon.get(60)
            ),
            predicted_temperature_3h_c=number(
                prediction_by_horizon.get(180)
            ),
            predicted_temperature_6h_c=number(
                prediction_by_horizon.get(360)
            ),
        )

    @property
    def running(self) -> bool:
        return self.state == "RUNNING"

    @property
    def blocked_by_infrastructure(self) -> bool:
        return not self.safety_safe or not self.device_ready

    @property
    def minimum_off_active(self) -> bool:
        return self.remaining_minimum_off_seconds > 0

    @property
    def minimum_on_active(self) -> bool:
        return self.remaining_minimum_on_seconds > 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "state": self.state,
            "running": self.running,
            "indoor_temperature_c": self.indoor_temperature_c,
            "cooling_power_kw": self.cooling_power_kw,
            "thermal_available": self.thermal_available,
            "safety_safe": self.safety_safe,
            "device_ready": self.device_ready,
            "blocked_by_infrastructure": (
                self.blocked_by_infrastructure
            ),
            "remaining_minimum_off_seconds": (
                self.remaining_minimum_off_seconds
            ),
            "remaining_minimum_on_seconds": (
                self.remaining_minimum_on_seconds
            ),
            "predicted_temperature_1h_c": (
                self.predicted_temperature_1h_c
            ),
            "predicted_temperature_3h_c": (
                self.predicted_temperature_3h_c
            ),
            "predicted_temperature_6h_c": (
                self.predicted_temperature_6h_c
            ),
        }
