from __future__ import annotations

import math
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def number(value: Any, default: float | None = None) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return default
    return result if math.isfinite(result) else default


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


@dataclass(frozen=True, slots=True)
class SimulationInput:
    indoor_c: float
    outdoor_c: float
    humidity_percent: float
    floor_c: float
    source_c: float
    cooling_power_kw: float
    building_capacity_kwh_per_c: float
    heat_gain_kw_per_c: float
    pump_power_kw: float
    comfort_target_c: float
    minimum_dew_margin_c: float


class ThermalSimulator:
    """Simulateur consultatif simple, déterministe et sans commande matérielle."""

    HORIZONS_MINUTES = (30, 60, 120, 240)

    def __init__(self) -> None:
        self.default_capacity = max(1.0, float(os.getenv("GEOCOOLING_BUILDING_CAPACITY_KWH_C", "18.0")))
        self.default_heat_gain = max(0.01, float(os.getenv("GEOCOOLING_HEAT_GAIN_KW_C", "0.22")))
        self.default_pump_power = max(0.0, float(os.getenv("GEOCOOLING_PUMP_POWER_KW", "0.15")))
        self.default_cooling_power = max(0.0, float(os.getenv("GEOCOOLING_NOMINAL_POWER_KW", "8.0")))
        self.comfort_target = float(os.getenv("GEOCOOLING_COMFORT_TARGET_C", "24.0"))
        self.minimum_dew_margin = max(0.0, float(os.getenv("GEOCOOLING_MIN_DEW_POINT_MARGIN_C", "3.0")))

    @staticmethod
    def dew_point_c(temperature_c: float, humidity_percent: float) -> float:
        humidity = clamp(humidity_percent, 1.0, 100.0)
        a, b = 17.62, 243.12
        gamma = (a * temperature_c) / (b + temperature_c) + math.log(humidity / 100.0)
        return (b * gamma) / (a - gamma)

    def simulate(self, data: SimulationInput, *, strategy: str, uncertainty: float = 1.0) -> dict[str, Any]:
        strategy = strategy.upper()
        delay_minutes = 45 if strategy == "WAIT_45" else 0
        active = strategy in {"START_NOW", "WAIT_45", "MAINTAIN"}
        indoor = data.indoor_c
        floor = data.floor_c
        runtime_minutes = 0.0
        energy_removed_kwh = 0.0
        electrical_kwh = 0.0
        points: dict[str, dict[str, Any]] = {}
        dew_point = self.dew_point_c(data.indoor_c, data.humidity_percent)
        minimum_floor = dew_point + data.minimum_dew_margin_c

        elapsed = 0
        step_minutes = 5
        for horizon in self.HORIZONS_MINUTES:
            while elapsed < horizon:
                running = active and elapsed >= delay_minutes
                heat_gain_kw = max(0.0, (data.outdoor_c - indoor) * data.heat_gain_kw_per_c * uncertainty)
                useful_cooling_kw = data.cooling_power_kw / max(0.7, uncertainty) if running else 0.0
                # La puissance utile est réduite progressivement à l'approche de la consigne.
                modulation = clamp((indoor - data.comfort_target_c + 0.8) / 2.0, 0.15, 1.0)
                useful_cooling_kw *= modulation
                dt_h = step_minutes / 60.0
                indoor += (heat_gain_kw - useful_cooling_kw) * dt_h / data.building_capacity_kwh_per_c
                target_floor = max(minimum_floor, indoor - (2.4 if running else 0.3))
                floor += (target_floor - floor) * min(1.0, dt_h / 0.65)
                if running:
                    runtime_minutes += step_minutes
                    energy_removed_kwh += useful_cooling_kw * dt_h
                    electrical_kwh += data.pump_power_kw * dt_h
                elapsed += step_minutes

            margin = floor - dew_point
            condensation_risk = clamp((data.minimum_dew_margin_c - margin + 1.0) / 4.0 * 100.0, 0.0, 100.0)
            comfort_index = clamp(100.0 - abs(indoor - data.comfort_target_c) * 25.0, 0.0, 100.0)
            points[f"{horizon}m"] = {
                "indoor_temperature_c": round(indoor, 2),
                "floor_temperature_c": round(floor, 2),
                "runtime_minutes": int(round(runtime_minutes)),
                "cooling_energy_kwh": round(energy_removed_kwh, 3),
                "electrical_energy_kwh": round(electrical_kwh, 3),
                "dew_point_c": round(dew_point, 2),
                "dew_point_margin_c": round(margin, 2),
                "condensation_risk_percent": round(condensation_risk, 1),
                "comfort_index": round(comfort_index, 1),
            }
        return points


class DecisionCostEngine:
    def evaluate(self, points: dict[str, dict[str, Any]], target_c: float) -> dict[str, Any]:
        final = points["240m"]
        comfort = clamp(100.0 - abs(float(final["indoor_temperature_c"]) - target_c) * 30.0, 0.0, 100.0)
        energy_penalty = min(35.0, float(final["electrical_energy_kwh"]) * 40.0)
        wear_penalty = min(15.0, float(final["runtime_minutes"]) / 240.0 * 15.0)
        safety_penalty = float(final["condensation_risk_percent"]) * 0.8
        score = comfort - energy_penalty - wear_penalty - safety_penalty
        return {
            "comfort_benefit": round(comfort, 1),
            "energy_penalty": round(energy_penalty, 1),
            "wear_penalty": round(wear_penalty, 1),
            "safety_penalty": round(safety_penalty, 1),
            "total_score": round(score, 1),
        }


class GeoCoolingForecastEngine:
    """Agrège les données réelles puis compare des stratégies, en lecture seule."""

    STRATEGIES = ("START_NOW", "WAIT_45", "OFF")
    UNCERTAINTIES = {"optimistic": 0.85, "normal": 1.0, "pessimistic": 1.15}

    def __init__(self, controller: Any) -> None:
        self.controller = controller
        self.simulator = ThermalSimulator()
        self.cost_engine = DecisionCostEngine()

    @staticmethod
    def _latest(thermal: dict[str, Any]) -> dict[str, Any]:
        latest = thermal.get("latest")
        return latest if isinstance(latest, dict) else {}

    def _input(self) -> tuple[SimulationInput, list[str]]:
        thermal = self.controller.thermal_status()
        latest = self._latest(thermal)
        assumptions: list[str] = []

        def pick(keys: tuple[str, ...], default: float, label: str) -> float:
            for source in (latest, thermal):
                for key in keys:
                    value = number(source.get(key))
                    if value is not None:
                        return value
            assumptions.append(f"{label}: valeur par défaut {default}")
            return default

        indoor = pick(("indoor_temperature_c",), 25.0, "température intérieure")
        outdoor = pick(("outdoor_temperature_c",), indoor + 4.0, "température extérieure")
        humidity = pick(("indoor_humidity_percent",), 50.0, "humidité intérieure")
        floor = pick(("floor_surface_temperature_c", "floor_temperature_c", "floor_supply_temperature_c"), indoor - 0.5, "température plancher")
        source = pick(("source_inlet_temperature_c",), 13.0, "température source")
        power = number(thermal.get("cooling_power_kw"))
        if power is None or power <= 0:
            power = self.simulator.default_cooling_power
            assumptions.append(f"puissance frigorifique: valeur nominale {power}")

        return SimulationInput(
            indoor_c=indoor,
            outdoor_c=outdoor,
            humidity_percent=humidity,
            floor_c=floor,
            source_c=source,
            cooling_power_kw=power,
            building_capacity_kwh_per_c=self.simulator.default_capacity,
            heat_gain_kw_per_c=self.simulator.default_heat_gain,
            pump_power_kw=self.simulator.default_pump_power,
            comfort_target_c=self.simulator.comfort_target,
            minimum_dew_margin_c=self.simulator.minimum_dew_margin,
        ), assumptions

    def scenarios(self) -> dict[str, Any]:
        data, assumptions = self._input()
        scenarios: list[dict[str, Any]] = []
        for strategy in self.STRATEGIES:
            variants = {
                name: self.simulator.simulate(data, strategy=strategy, uncertainty=factor)
                for name, factor in self.UNCERTAINTIES.items()
            }
            cost = self.cost_engine.evaluate(variants["normal"], data.comfort_target_c)
            scenarios.append({"strategy": strategy, "cost": cost, "variants": variants})

        scenarios.sort(key=lambda item: item["cost"]["total_score"], reverse=True)
        return {
            "generated_at": utc_now_iso(),
            "read_only": True,
            "model": "C023.1-first-order-multi-scenario",
            "input": {
                "indoor_temperature_c": data.indoor_c,
                "outdoor_temperature_c": data.outdoor_c,
                "humidity_percent": data.humidity_percent,
                "floor_temperature_c": data.floor_c,
                "source_temperature_c": data.source_c,
                "cooling_power_kw": data.cooling_power_kw,
                "comfort_target_c": data.comfort_target_c,
            },
            "assumptions": assumptions,
            "recommended_strategy": scenarios[0]["strategy"],
            "scenarios": scenarios,
        }

    def forecast(self) -> dict[str, Any]:
        payload = self.scenarios()
        best = payload["scenarios"][0]
        normal = best["variants"]["normal"]
        forecast = {}
        for key, point in normal.items():
            forecast[key] = {
                "decision": best["strategy"],
                "indoor_temperature_c": point["indoor_temperature_c"],
                "runtime_minutes": point["runtime_minutes"],
                "comfort_index": point["comfort_index"],
                "condensation_risk_percent": point["condensation_risk_percent"],
            }
        return {
            "generated_at": payload["generated_at"],
            "read_only": True,
            "model": payload["model"],
            "recommended_strategy": best["strategy"],
            "decision_cost": best["cost"],
            "forecast": forecast,
            "assumptions": payload["assumptions"],
        }
