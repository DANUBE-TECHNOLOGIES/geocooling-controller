from __future__ import annotations

import math
from dataclasses import asdict, dataclass
from typing import Any, Callable, Mapping

NumberParser = Callable[[Any], float | None]


@dataclass(frozen=True, slots=True)
class EnergyAssessment:
    available_power_kw: float | None
    measured_power_kw: float | None
    theoretical_power_kw: float | None
    efficiency_percent: int | None
    confidence: int
    score: int
    useful: bool | None
    limitation: str | None
    source: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class GeoCoolingEnergyModel:
    """Estime la capacité frigorifique sans commander le matériel.

    La puissance hydraulique est calculée avec Q = débit × Cp × ΔT.
    Pour de l'eau, 1 l/min et 1 K représentent environ 0,0698 kW.
    """

    WATER_KW_PER_L_MIN_K = 0.06977

    def __init__(
        self,
        *,
        minimum_useful_power_kw: float = 0.8,
        nominal_power_kw: float = 8.0,
    ) -> None:
        self.minimum_useful_power_kw = max(0.0, float(minimum_useful_power_kw))
        self.nominal_power_kw = max(0.1, float(nominal_power_kw))

    @staticmethod
    def _finite(value: float | None) -> float | None:
        if value is None or not math.isfinite(value):
            return None
        return value

    @staticmethod
    def _clamp(value: float, minimum: float = 0.0, maximum: float = 100.0) -> int:
        return int(round(max(minimum, min(maximum, value))))

    def evaluate(
        self,
        *,
        thermal: Mapping[str, Any],
        latest: Mapping[str, Any],
        number_parser: NumberParser,
    ) -> EnergyAssessment:
        measured = self._finite(number_parser(thermal.get("cooling_power_kw")))
        flow = self._finite(number_parser(latest.get("flow_rate_l_min")))
        supply = self._finite(number_parser(latest.get("floor_supply_temperature_c")))
        return_temp = self._finite(number_parser(latest.get("floor_return_temperature_c")))
        source_inlet = self._finite(number_parser(latest.get("source_inlet_temperature_c")))
        source_outlet = self._finite(number_parser(latest.get("source_outlet_temperature_c")))

        theoretical: float | None = None
        delta_t: float | None = None
        source = "unavailable"
        confidence = 0

        if flow is not None and flow > 0:
            if supply is not None and return_temp is not None:
                delta_t = max(0.0, return_temp - supply)
                theoretical = flow * self.WATER_KW_PER_L_MIN_K * delta_t
                source = "floor_loop"
                confidence = 85
            elif source_inlet is not None and source_outlet is not None:
                delta_t = abs(source_outlet - source_inlet)
                theoretical = flow * self.WATER_KW_PER_L_MIN_K * delta_t
                source = "source_loop"
                confidence = 75

        available: float | None
        if measured is not None and measured >= 0:
            available = measured
            source = "measured"
            confidence = 95 if theoretical is not None else 90
        else:
            available = theoretical

        if available is None:
            return EnergyAssessment(
                available_power_kw=None,
                measured_power_kw=measured,
                theoretical_power_kw=theoretical,
                efficiency_percent=None,
                confidence=0,
                score=50,
                useful=None,
                limitation="Capacité énergétique non mesurable",
                source=source,
            )

        available = max(0.0, available)
        useful = available >= self.minimum_useful_power_kw
        score = self._clamp(available / self.nominal_power_kw * 100.0)

        efficiency: int | None = None
        if measured is not None and theoretical is not None and theoretical > 0:
            efficiency = self._clamp(measured / theoretical * 100.0)

        limitation: str | None = None
        if flow is not None and flow <= 0:
            limitation = "Débit hydraulique nul"
        elif not useful:
            limitation = (
                f"Puissance disponible insuffisante ({available:.2f} kW < "
                f"{self.minimum_useful_power_kw:.2f} kW)"
            )
        elif source_inlet is not None and source_inlet >= 18.0:
            limitation = f"Source chaude ({source_inlet:.1f} °C)"

        return EnergyAssessment(
            available_power_kw=round(available, 3),
            measured_power_kw=None if measured is None else round(measured, 3),
            theoretical_power_kw=None if theoretical is None else round(theoretical, 3),
            efficiency_percent=efficiency,
            confidence=confidence,
            score=score,
            useful=useful,
            limitation=limitation,
            source=source,
        )
