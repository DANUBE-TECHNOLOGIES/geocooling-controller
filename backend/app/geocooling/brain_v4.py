from __future__ import annotations

import copy
import json
import math
import os
import threading
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


def dew_point_c(temperature_c: float, humidity_percent: float) -> float:
    humidity = max(1.0, min(100.0, humidity_percent))
    a, b = 17.62, 243.12
    gamma = math.log(humidity / 100.0) + (a * temperature_c) / (b + temperature_c)
    return (b * gamma) / (a - gamma)


class GeoCoolingBrainV4:
    """Thermal learning and predictive advisor. Never commands hardware."""

    VERSION = "BRAIN-V4-1.0"

    def __init__(self, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv("GEOCOOLING_BRAIN_V4_PATH", str(base / "brain-v4-model.json")))
        self._lock = threading.RLock()
        self.alpha = max(0.02, min(0.5, float(os.getenv("GEOCOOLING_BRAIN_V4_ALPHA", "0.15"))))
        self.comfort_target_c = float(os.getenv("GEOCOOLING_COMFORT_TARGET_C", "24.0"))
        self.start_threshold_c = float(os.getenv("GEOCOOLING_START_THRESHOLD_C", "25.0"))
        self.stop_threshold_c = float(os.getenv("GEOCOOLING_STOP_THRESHOLD_C", "23.8"))
        self.minimum_dew_margin_c = float(os.getenv("GEOCOOLING_MINIMUM_DEW_MARGIN_C", "3.0"))
        self.minimum_runtime_minutes = int(os.getenv("GEOCOOLING_MIN_RUNTIME_MINUTES", "15"))
        self.maximum_runtime_minutes = int(os.getenv("GEOCOOLING_MAX_RUNTIME_MINUTES", "180"))
        self.valve_lead_seconds = int(os.getenv("GEOCOOLING_VALVE_LEAD_SECONDS", "20"))
        self.pump_overrun_seconds = int(os.getenv("GEOCOOLING_PUMP_OVERRUN_SECONDS", "30"))
        self._model: dict[str, Any] = {
            "passive_rate_per_hour": None,
            "active_cooling_rate_c_per_hour": None,
            "samples": 0,
            "passive_samples": 0,
            "active_samples": 0,
            "last_observation_at": None,
        }
        self._weather: dict[str, Any] = {}
        self._load()

    def _load(self) -> None:
        try:
            if self.path.exists():
                value = json.loads(self.path.read_text(encoding="utf-8"))
                if isinstance(value, dict):
                    self._model.update(value.get("model") or {})
                    self._weather = value.get("weather") or {}
        except Exception:
            pass

    def _persist(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            temp = self.path.with_suffix(".tmp")
            temp.write_text(json.dumps({"model": self._model, "weather": self._weather}, ensure_ascii=False, indent=2), encoding="utf-8")
            temp.replace(self.path)
        except Exception:
            pass

    def update_weather(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._lock:
            self._weather = {
                "outdoor_temperature_c": finite(payload.get("outdoor_temperature_c")),
                "forecast_max_6h_c": finite(payload.get("forecast_max_6h_c")),
                "forecast_max_24h_c": finite(payload.get("forecast_max_24h_c")),
                "solar_radiation_w_m2": finite(payload.get("solar_radiation_w_m2")),
                "source": str(payload.get("source") or "external"),
                "updated_at": utc_now_iso(),
            }
            self._persist()
            return copy.deepcopy(self._weather)

    def observe(self, previous: dict[str, Any], current: dict[str, Any]) -> dict[str, Any]:
        previous_indoor = finite(previous.get("indoor_temperature_c"))
        current_indoor = finite(current.get("indoor_temperature_c"))
        previous_at = previous.get("timestamp") or previous.get("at")
        current_at = current.get("timestamp") or current.get("at")
        if previous_indoor is None or current_indoor is None or not previous_at or not current_at:
            return {"accepted": False, "reason": "missing temperature or timestamp"}
        try:
            start = datetime.fromisoformat(str(previous_at).replace("Z", "+00:00"))
            end = datetime.fromisoformat(str(current_at).replace("Z", "+00:00"))
        except ValueError:
            return {"accepted": False, "reason": "invalid timestamp"}
        elapsed_h = (end - start).total_seconds() / 3600.0
        if elapsed_h < (2 / 60) or elapsed_h > 6:
            return {"accepted": False, "reason": "observation interval outside 2 minutes to 6 hours"}
        rate = (current_indoor - previous_indoor) / elapsed_h
        if abs(rate) > 5:
            return {"accepted": False, "reason": "implausible thermal rate"}
        running = bool(previous.get("pump_running")) and bool(current.get("pump_running"))
        field = "active_cooling_rate_c_per_hour" if running else "passive_rate_per_hour"
        observation = abs(rate) if running else rate
        with self._lock:
            old = finite(self._model.get(field))
            learned = observation if old is None else old * (1 - self.alpha) + observation * self.alpha
            self._model[field] = round(learned, 5)
            self._model["samples"] = int(self._model.get("samples") or 0) + 1
            counter = "active_samples" if running else "passive_samples"
            self._model[counter] = int(self._model.get(counter) or 0) + 1
            self._model["last_observation_at"] = utc_now_iso()
            self._persist()
        return {"accepted": True, "mode": "ACTIVE" if running else "PASSIVE", "observed_rate_c_per_hour": round(rate, 4), "model": self.model_status()}

    @staticmethod
    def _latest(thermal: dict[str, Any] | None) -> dict[str, Any]:
        thermal = thermal or {}
        latest = thermal.get("latest")
        return latest if isinstance(latest, dict) else thermal

    def model_status(self) -> dict[str, Any]:
        with self._lock:
            samples = int(self._model.get("samples") or 0)
            confidence = min(95, 20 + samples * 5)
            return {
                "version": self.VERSION,
                "learning_mode": "OBSERVE_ONLY",
                "confidence": confidence,
                "ready": samples >= 6 and int(self._model.get("active_samples") or 0) >= 2,
                **copy.deepcopy(self._model),
                "weather": copy.deepcopy(self._weather),
            }

    def analyze(self, thermal: dict[str, Any] | None, safety: dict[str, Any]) -> dict[str, Any]:
        latest = self._latest(thermal)
        indoor = finite(latest.get("indoor_temperature_c"))
        humidity = finite(latest.get("indoor_humidity_percent") or latest.get("humidity_percent"))
        supply = finite(latest.get("supply_temperature_c"))
        floor = finite(latest.get("floor_surface_temperature_c") or latest.get("floor_temperature_c"))
        outdoor = finite(latest.get("outdoor_temperature_c")) or finite(self._weather.get("outdoor_temperature_c"))
        forecast_6h = finite(self._weather.get("forecast_max_6h_c"))
        model = self.model_status()
        passive_rate = finite(model.get("passive_rate_per_hour"))
        active_rate = finite(model.get("active_cooling_rate_c_per_hour"))

        dew = dew_point_c(indoor, humidity) if indoor is not None and humidity is not None else None
        coldest_surface = min(value for value in (supply, floor) if value is not None) if any(value is not None for value in (supply, floor)) else None
        margin = coldest_surface - dew if coldest_surface is not None and dew is not None else None
        condensation_safe = margin is not None and margin >= self.minimum_dew_margin_c

        predicted_1h = None
        if indoor is not None:
            natural = passive_rate
            if natural is None and outdoor is not None:
                natural = max(-0.5, min(1.5, (outdoor - indoor) * 0.08))
            predicted_1h = indoor + (natural or 0.0)
            if forecast_6h is not None and forecast_6h > indoor:
                predicted_1h += min(0.5, (forecast_6h - indoor) * 0.05)

        blockers: list[str] = []
        if not safety.get("safe", False): blockers.append("safety-manager")
        if indoor is None: blockers.append("indoor-temperature-missing")
        if humidity is None: blockers.append("humidity-missing")
        if coldest_surface is None: blockers.append("surface-or-supply-temperature-missing")
        if margin is not None and margin < self.minimum_dew_margin_c: blockers.append("condensation-risk")

        action = "WAIT"
        runtime = 0
        strategy = "HOLD_SAFE_STATE"
        target_supply = None if dew is None else round(dew + self.minimum_dew_margin_c, 2)
        if not blockers and indoor is not None:
            heat_pressure = max(indoor, predicted_1h or indoor, forecast_6h or indoor)
            if heat_pressure >= self.start_threshold_c:
                action = "COOL"
                strategy = "PREDICTIVE_COOLING"
                excess = max(0.0, heat_pressure - self.comfort_target_c)
                effective_rate = active_rate if active_rate and active_rate >= 0.05 else 0.35
                runtime = int(round((excess / effective_rate) * 60))
                runtime = max(self.minimum_runtime_minutes, min(self.maximum_runtime_minutes, runtime))
            elif indoor <= self.stop_threshold_c:
                action = "STOP"
                strategy = "COMFORT_TARGET_REACHED"

        confidence = model["confidence"]
        if indoor is None or humidity is None: confidence = min(confidence, 35)
        reasons = [
            f"indoor={indoor}" if indoor is not None else "indoor missing",
            f"predicted_1h={round(predicted_1h, 2)}" if predicted_1h is not None else "prediction unavailable",
            f"dew_point={round(dew, 2)}" if dew is not None else "dew point unavailable",
            f"condensation_margin={round(margin, 2)}" if margin is not None else "condensation margin unavailable",
        ]
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_command_authorized": False,
            "recommended_action": action,
            "recommended_runtime_minutes": runtime,
            "optimization_strategy": strategy,
            "confidence": confidence,
            "predicted_indoor_temperature_1h_c": None if predicted_1h is None else round(predicted_1h, 2),
            "dew_point_c": None if dew is None else round(dew, 2),
            "condensation_margin_c": None if margin is None else round(margin, 2),
            "minimum_condensation_margin_c": self.minimum_dew_margin_c,
            "minimum_safe_supply_temperature_c": target_supply,
            "condensation_safe": condensation_safe,
            "hydraulic_sequence": {
                "valve_lead_seconds": self.valve_lead_seconds,
                "minimum_pump_runtime_minutes": self.minimum_runtime_minutes,
                "pump_overrun_seconds": self.pump_overrun_seconds,
                "anti_short_cycle": True,
            },
            "blocking_conditions": blockers,
            "decision_reasons": reasons,
            "model": model,
            "weather": copy.deepcopy(self._weather),
        }
