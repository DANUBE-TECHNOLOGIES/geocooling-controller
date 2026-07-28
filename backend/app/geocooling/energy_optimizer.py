from __future__ import annotations

import json
import math
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite(value: Any) -> float | None:
    try:
        number = float(value)
    except (TypeError, ValueError):
        return None
    return number if math.isfinite(number) else None


class GeoCoolingEnergyOptimizer:
    """Advisory-only 24 h scheduler minimizing runtime, starts and discomfort."""

    VERSION = "H020-ENERGY-OPTIMIZER-1.0"

    def __init__(self, model: Any, validation: Any, path: str | None = None) -> None:
        self.model = model
        self.validation = validation
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_ENERGY_OPTIMIZER_PATH", str(base / "energy-optimizer.json")))
        self.electrical_power_kw = float(os.getenv("GEOCOOLING_ELECTRICAL_POWER_KW", "0.45"))
        self.minimum_cycle_minutes = int(os.getenv("GEOCOOLING_MINIMUM_CYCLE_MINUTES", "30"))
        self.maximum_cycle_minutes = int(os.getenv("GEOCOOLING_MAXIMUM_CYCLE_MINUTES", "360"))
        self.start_penalty_kwh = float(os.getenv("GEOCOOLING_START_PENALTY_KWH", "0.08"))
        self.comfort_weight = float(os.getenv("GEOCOOLING_COMFORT_WEIGHT", "8"))
        self.history: list[dict[str, Any]] = []
        self.last_plan: dict[str, Any] | None = None
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            if isinstance(data.get("history"), list):
                self.history = data["history"][-100:]
            if isinstance(data.get("last_plan"), dict):
                self.last_plan = data["last_plan"]
        except Exception:
            return

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({"last_plan": self.last_plan, "history": self.history[-100:]}, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except Exception:
            pass

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(), "version": self.VERSION, "advisory_only": True,
            "physical_activation_allowed": False, "hardware_touched": False,
            "parameters": {
                "electrical_power_kw": self.electrical_power_kw,
                "minimum_cycle_minutes": self.minimum_cycle_minutes,
                "maximum_cycle_minutes": self.maximum_cycle_minutes,
                "start_penalty_kwh": self.start_penalty_kwh,
                "comfort_weight": self.comfort_weight,
            },
            "last_plan": self.last_plan,
            "assessment_count": len(self.history),
        }

    def _forecast(self, payload: dict[str, Any]) -> list[dict[str, float]]:
        forecast = payload.get("forecast")
        if not isinstance(forecast, list) or not 1 <= len(forecast) <= 24:
            raise ValueError("forecast must contain between 1 and 24 hourly entries")
        normalized = []
        for index, row in enumerate(forecast):
            if not isinstance(row, dict):
                raise ValueError(f"forecast entry {index} must be an object")
            outdoor = finite(row.get("outdoor_temperature_c"))
            humidity = finite(row.get("humidity_percent"))
            solar = finite(row.get("solar_factor"))
            if outdoor is None or humidity is None:
                raise ValueError(f"forecast entry {index} requires outdoor_temperature_c and humidity_percent")
            normalized.append({"outdoor_temperature_c": outdoor, "humidity_percent": humidity, "solar_factor": 0.0 if solar is None else max(0.0, min(2.0, solar))})
        return normalized

    def _simulate(self, *, indoor: float, target: float, forecast: list[dict[str, float]], start: int | None, duration: int) -> dict[str, Any]:
        temperature = indoor
        trace = []
        discomfort = 0.0
        blocked = False
        for hour, weather in enumerate(forecast):
            cooling = start is not None and start <= hour < start + duration
            result = self.validation.predict({
                "indoor_temperature_c": temperature,
                "outdoor_temperature_c": weather["outdoor_temperature_c"],
                "humidity_percent": weather["humidity_percent"],
                "target_temperature_c": target,
                "hours": 1,
                "cooling_enabled": cooling,
                "solar_factor": weather["solar_factor"],
            })
            # validation prediction is promoted-parameter aware but only returns final temperature.
            temperature = float(result["prediction"]["final_temperature_c"])
            envelope = self.model.condensation_envelope(temperature, weather["humidity_percent"])
            if cooling and not envelope.get("available"):
                blocked = True
            excess = max(0.0, temperature - target)
            discomfort += excess * excess
            trace.append({"hour": hour, "temperature_c": round(temperature, 3), "cooling": cooling, "outdoor_temperature_c": weather["outdoor_temperature_c"]})
        runtime_h = float(duration)
        energy_kwh = runtime_h * self.electrical_power_kw + (self.start_penalty_kwh if duration else 0.0)
        score = energy_kwh + self.comfort_weight * discomfort + (10000.0 if blocked else 0.0)
        return {"trace": trace, "final_temperature_c": round(temperature, 3), "discomfort_degree_hours_squared": round(discomfort, 4), "estimated_energy_kwh": round(energy_kwh, 4), "score": round(score, 4), "condensation_interlock": blocked}

    def optimize(self, payload: dict[str, Any]) -> dict[str, Any]:
        indoor = finite(payload.get("indoor_temperature_c"))
        target = finite(payload.get("target_temperature_c"))
        if indoor is None or target is None:
            raise ValueError("indoor_temperature_c and target_temperature_c are required")
        forecast = self._forecast(payload)
        max_hours = min(len(forecast), max(1, math.ceil(self.maximum_cycle_minutes / 60)))
        min_hours = max(1, math.ceil(self.minimum_cycle_minutes / 60))
        candidates = [(None, 0)]
        for duration in range(min_hours, max_hours + 1):
            for start in range(0, len(forecast) - duration + 1):
                candidates.append((start, duration))
        evaluated = []
        for start, duration in candidates:
            simulation = self._simulate(indoor=indoor, target=target, forecast=forecast, start=start, duration=duration)
            evaluated.append({"start_hour": start, "duration_hours": duration, **simulation})
        best = min(evaluated, key=lambda item: item["score"])
        baseline = next(item for item in evaluated if item["duration_hours"] == 0)
        runtime_minutes = int(best["duration_hours"] * 60)
        thermal_gain = max(0.0, baseline["final_temperature_c"] - best["final_temperature_c"])
        avoided_discomfort = max(0.0, baseline["discomfort_degree_hours_squared"] - best["discomfort_degree_hours_squared"])
        plan = {
            "generated_at": utc_now_iso(), "version": self.VERSION, "horizon_hours": len(forecast),
            "strategy": "SINGLE_LONG_CYCLE_MINIMUM_COST", "recommended_action": "COOL" if runtime_minutes else "HOLD",
            "recommended_start_hour": best["start_hour"], "recommended_runtime_minutes": runtime_minutes,
            "estimated_energy_kwh": best["estimated_energy_kwh"], "estimated_starts": 1 if runtime_minutes else 0,
            "thermal_gain_c": round(thermal_gain, 3), "avoided_discomfort_score": round(avoided_discomfort, 3),
            "efficiency_index": round((thermal_gain / best["estimated_energy_kwh"]), 3) if best["estimated_energy_kwh"] else 0.0,
            "baseline": {"final_temperature_c": baseline["final_temperature_c"], "discomfort_degree_hours_squared": baseline["discomfort_degree_hours_squared"]},
            "optimized": {key: best[key] for key in ("final_temperature_c", "discomfort_degree_hours_squared", "estimated_energy_kwh", "condensation_interlock")},
            "schedule": [{"hour": row["hour"], "cooling": row["cooling"], "predicted_temperature_c": row["temperature_c"]} for row in best["trace"]],
            "physical_activation_allowed": False, "hardware_touched": False,
        }
        self.last_plan = plan
        self._save()
        return plan

    def assess(self, payload: dict[str, Any]) -> dict[str, Any]:
        predicted = finite(payload.get("predicted_final_temperature_c"))
        observed = finite(payload.get("observed_final_temperature_c"))
        planned = finite(payload.get("planned_energy_kwh"))
        actual = finite(payload.get("actual_energy_kwh"))
        target = finite(payload.get("target_temperature_c"))
        if None in (predicted, observed, planned, actual, target):
            raise ValueError("predicted_final_temperature_c, observed_final_temperature_c, planned_energy_kwh, actual_energy_kwh and target_temperature_c are required")
        error = observed - predicted
        comfort_deviation = max(0.0, observed - target)
        energy_variance = actual - planned
        grade = "GOOD" if abs(error) <= 0.5 and comfort_deviation <= 0.5 and energy_variance <= 0.15 else "REVIEW"
        assessment = {
            "assessed_at": utc_now_iso(), "prediction_error_c": round(error, 3),
            "absolute_prediction_error_c": round(abs(error), 3), "comfort_deviation_c": round(comfort_deviation, 3),
            "energy_variance_kwh": round(energy_variance, 3), "performance": grade,
            "physical_activation_allowed": False, "hardware_touched": False,
        }
        self.history.append(assessment)
        self._save()
        return assessment

    def assessments(self, limit: int = 20) -> list[dict[str, Any]]:
        return self.history[-max(1, min(100, int(limit))):]
