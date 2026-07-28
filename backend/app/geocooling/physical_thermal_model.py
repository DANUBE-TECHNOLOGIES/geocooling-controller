from __future__ import annotations

import math
import os
from datetime import datetime, timezone
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


class GeoCoolingPhysicalThermalModel:
    """First-order building model used for advisory simulation only."""

    VERSION = "H017-PHYSICAL-THERMAL-1.0"

    def __init__(self) -> None:
        self.floor_area_m2 = float(os.getenv("GEOCOOLING_BUILDING_AREA_M2", "200"))
        self.heat_capacity_kwh_per_c = float(os.getenv("GEOCOOLING_HEAT_CAPACITY_KWH_PER_C", "16"))
        self.heat_loss_kw_per_c = float(os.getenv("GEOCOOLING_HEAT_LOSS_KW_PER_C", "0.32"))
        self.nominal_cooling_kw = float(os.getenv("GEOCOOLING_NOMINAL_COOLING_KW", "8"))
        self.solar_gain_kw = float(os.getenv("GEOCOOLING_SOLAR_GAIN_KW", "1.2"))
        self.internal_gain_kw = float(os.getenv("GEOCOOLING_INTERNAL_GAIN_KW", "0.8"))
        self.minimum_dew_margin_c = float(os.getenv("GEOCOOLING_MINIMUM_DEW_MARGIN_C", "3"))
        self.minimum_supply_c = float(os.getenv("GEOCOOLING_MINIMUM_SUPPLY_C", "16"))
        self.maximum_runtime_minutes = int(os.getenv("GEOCOOLING_MAX_RUNTIME_MINUTES", "180"))

    def status(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_activation_allowed": False,
            "parameters": {
                "floor_area_m2": self.floor_area_m2,
                "heat_capacity_kwh_per_c": self.heat_capacity_kwh_per_c,
                "heat_loss_kw_per_c": self.heat_loss_kw_per_c,
                "nominal_cooling_kw": self.nominal_cooling_kw,
                "solar_gain_kw": self.solar_gain_kw,
                "internal_gain_kw": self.internal_gain_kw,
                "minimum_dew_margin_c": self.minimum_dew_margin_c,
                "minimum_supply_c": self.minimum_supply_c,
            },
        }

    def condensation_envelope(self, indoor_temperature_c: Any, humidity_percent: Any) -> dict[str, Any]:
        indoor = finite(indoor_temperature_c)
        humidity = finite(humidity_percent)
        if indoor is None or humidity is None:
            return {
                "available": False,
                "reason": "indoor temperature and humidity required",
                "minimum_safe_supply_c": None,
            }
        dew = dew_point_c(indoor, humidity)
        safe_supply = max(self.minimum_supply_c, dew + self.minimum_dew_margin_c)
        return {
            "available": True,
            "dew_point_c": round(dew, 2),
            "minimum_safe_supply_c": round(safe_supply, 2),
            "dew_margin_c": self.minimum_dew_margin_c,
        }

    def predict(self, payload: dict[str, Any]) -> dict[str, Any]:
        indoor = finite(payload.get("indoor_temperature_c"))
        outdoor = finite(payload.get("outdoor_temperature_c"))
        humidity = finite(payload.get("humidity_percent") or payload.get("indoor_humidity_percent"))
        target = finite(payload.get("target_temperature_c"))
        hours = finite(payload.get("hours")) or 1.0
        cooling_enabled = bool(payload.get("cooling_enabled", False))
        solar_factor = finite(payload.get("solar_factor"))
        if indoor is None or outdoor is None:
            raise ValueError("indoor_temperature_c and outdoor_temperature_c are required")
        hours = max(0.05, min(24.0, hours))
        solar_factor = 1.0 if solar_factor is None else max(0.0, min(2.0, solar_factor))

        envelope = self.condensation_envelope(indoor, humidity)
        cooling_kw = self.nominal_cooling_kw if cooling_enabled else 0.0
        envelope_blocked = cooling_enabled and not envelope.get("available")
        if envelope_blocked:
            cooling_kw = 0.0

        steps = max(1, int(math.ceil(hours * 12)))
        dt_h = hours / steps
        temperature = indoor
        trace: list[dict[str, Any]] = []
        for index in range(steps):
            envelope_gain_kw = self.heat_loss_kw_per_c * (outdoor - temperature)
            gains_kw = envelope_gain_kw + self.internal_gain_kw + self.solar_gain_kw * solar_factor
            net_kw = gains_kw - cooling_kw
            temperature += (net_kw / max(0.1, self.heat_capacity_kwh_per_c)) * dt_h
            trace.append({"minute": round((index + 1) * dt_h * 60), "temperature_c": round(temperature, 3)})

        runtime_minutes = 0
        if target is not None and cooling_enabled and cooling_kw > 0 and indoor > target:
            net_cooling_kw = cooling_kw - (
                self.heat_loss_kw_per_c * (outdoor - indoor)
                + self.internal_gain_kw
                + self.solar_gain_kw * solar_factor
            )
            if net_cooling_kw > 0.05:
                runtime_minutes = int(math.ceil(((indoor - target) * self.heat_capacity_kwh_per_c / net_cooling_kw) * 60))
                runtime_minutes = min(self.maximum_runtime_minutes, max(0, runtime_minutes))

        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "advisory_only": True,
            "physical_activation_allowed": False,
            "input": {
                "indoor_temperature_c": indoor,
                "outdoor_temperature_c": outdoor,
                "humidity_percent": humidity,
                "target_temperature_c": target,
                "hours": hours,
                "cooling_enabled": cooling_enabled,
                "solar_factor": solar_factor,
            },
            "prediction": {
                "final_temperature_c": round(temperature, 2),
                "temperature_change_c": round(temperature - indoor, 2),
                "recommended_runtime_minutes": runtime_minutes,
                "cooling_power_kw": round(cooling_kw, 2),
                "condensation_interlock": envelope_blocked,
            },
            "condensation": envelope,
            "trace": trace,
        }

    def optimize(self, payload: dict[str, Any]) -> dict[str, Any]:
        base = dict(payload)
        base["cooling_enabled"] = True
        target = finite(base.get("target_temperature_c"))
        if target is None:
            raise ValueError("target_temperature_c is required")
        simulation = self.predict(base)
        runtime = simulation["prediction"]["recommended_runtime_minutes"]
        current = finite(base.get("indoor_temperature_c"))
        if simulation["prediction"]["condensation_interlock"]:
            action, strategy = "WAIT", "CONDENSATION_DATA_REQUIRED"
        elif current is not None and current <= target:
            action, strategy = "STOP", "TARGET_ALREADY_REACHED"
        elif runtime > 0:
            action, strategy = "COOL", "MINIMUM_ENERGY_RUNTIME"
        else:
            action, strategy = "WAIT", "INSUFFICIENT_COOLING_CAPACITY"
        return {
            **simulation,
            "optimization": {
                "recommended_action": action,
                "strategy": strategy,
                "recommended_runtime_minutes": runtime,
                "hardware_touched": False,
            },
        }
