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


class GeoCoolingThermalModelLearning:
    """Bounded, persistent calibration of the advisory physical model."""

    VERSION = "H018-THERMAL-LEARNING-1.0"

    def __init__(self, model: Any, path: str | None = None) -> None:
        self.model = model
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_THERMAL_LEARNING_PATH", str(base / "thermal-model-learning.json")))
        self.maximum_samples = int(os.getenv("GEOCOOLING_THERMAL_LEARNING_MAX_SAMPLES", "500"))
        self.minimum_samples = int(os.getenv("GEOCOOLING_THERMAL_LEARNING_MIN_SAMPLES", "8"))
        self.learning_rate = float(os.getenv("GEOCOOLING_THERMAL_LEARNING_RATE", "0.08"))
        self.samples: list[dict[str, Any]] = []
        self.adjustments = {"heat_capacity_factor": 1.0, "cooling_power_factor": 1.0}
        self._load()

    def _load(self) -> None:
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            samples = data.get("samples", [])
            adjustments = data.get("adjustments", {})
            if isinstance(samples, list):
                self.samples = samples[-self.maximum_samples:]
            if isinstance(adjustments, dict):
                self.adjustments.update(adjustments)
        except Exception:
            return

    def _save(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temporary = self.path.with_suffix(self.path.suffix + ".tmp")
            temporary.write_text(json.dumps({"samples": self.samples, "adjustments": self.adjustments}, ensure_ascii=False, indent=2), encoding="utf-8")
            temporary.replace(self.path)
        except Exception:
            pass

    def _metrics(self) -> dict[str, Any]:
        errors = [float(item["error_c"]) for item in self.samples if finite(item.get("error_c")) is not None]
        if not errors:
            return {"sample_count": 0, "mae_c": None, "bias_c": None, "rmse_c": None}
        mae = sum(abs(value) for value in errors) / len(errors)
        bias = sum(errors) / len(errors)
        rmse = math.sqrt(sum(value * value for value in errors) / len(errors))
        return {"sample_count": len(errors), "mae_c": round(mae, 3), "bias_c": round(bias, 3), "rmse_c": round(rmse, 3)}

    def status(self) -> dict[str, Any]:
        metrics = self._metrics()
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_activation_allowed": False,
            "learning_enabled": True,
            "calibration_ready": metrics["sample_count"] >= self.minimum_samples,
            "metrics": metrics,
            "adjustments": {key: round(float(value), 4) for key, value in self.adjustments.items()},
        }

    def observe(self, payload: dict[str, Any]) -> dict[str, Any]:
        predicted = finite(payload.get("predicted_temperature_c"))
        observed = finite(payload.get("observed_temperature_c"))
        cooling_enabled = bool(payload.get("cooling_enabled", False))
        duration_minutes = finite(payload.get("duration_minutes"))
        if predicted is None or observed is None or duration_minutes is None:
            raise ValueError("predicted_temperature_c, observed_temperature_c and duration_minutes are required")
        if duration_minutes <= 0 or duration_minutes > 1440:
            raise ValueError("duration_minutes must be between 0 and 1440")
        error = observed - predicted
        sample = {
            "observed_at": utc_now_iso(),
            "predicted_temperature_c": predicted,
            "observed_temperature_c": observed,
            "error_c": round(error, 4),
            "cooling_enabled": cooling_enabled,
            "duration_minutes": duration_minutes,
        }
        self.samples.append(sample)
        self.samples = self.samples[-self.maximum_samples:]
        self._update_adjustments()
        self._save()
        return {"accepted": True, "sample": sample, "status": self.status(), "hardware_touched": False}

    def _update_adjustments(self) -> None:
        if len(self.samples) < self.minimum_samples:
            return
        recent = self.samples[-min(50, len(self.samples)):]
        active = [item for item in recent if item.get("cooling_enabled")]
        passive = [item for item in recent if not item.get("cooling_enabled")]
        rate = max(0.001, min(0.25, self.learning_rate))
        if passive:
            bias = sum(float(item["error_c"]) for item in passive) / len(passive)
            factor = float(self.adjustments["heat_capacity_factor"])
            factor *= 1.0 + max(-0.03, min(0.03, bias * rate * 0.1))
            self.adjustments["heat_capacity_factor"] = max(0.65, min(1.50, factor))
        if active:
            bias = sum(float(item["error_c"]) for item in active) / len(active)
            factor = float(self.adjustments["cooling_power_factor"])
            factor *= 1.0 - max(-0.04, min(0.04, bias * rate * 0.12))
            self.adjustments["cooling_power_factor"] = max(0.60, min(1.40, factor))

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        original_capacity = self.model.heat_capacity_kwh_per_c
        original_power = self.model.nominal_cooling_kw
        try:
            self.model.heat_capacity_kwh_per_c = original_capacity * float(self.adjustments["heat_capacity_factor"])
            self.model.nominal_cooling_kw = original_power * float(self.adjustments["cooling_power_factor"])
            result = self.model.predict(payload)
        finally:
            self.model.heat_capacity_kwh_per_c = original_capacity
            self.model.nominal_cooling_kw = original_power
        result["learning"] = self.status()
        return result

    def reset(self) -> dict[str, Any]:
        self.samples = []
        self.adjustments = {"heat_capacity_factor": 1.0, "cooling_power_factor": 1.0}
        self._save()
        return self.status()
