from __future__ import annotations

import copy
import json
import math
import os
import threading
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def finite_float(value: Any) -> float | None:
    if value is None:
        return None
    try:
        value = float(value)
    except (TypeError, ValueError):
        return None
    return value if math.isfinite(value) else None


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


@dataclass(slots=True)
class DigitalTwinInputs:
    indoor_temperature_c: float | None = None
    upstairs_temperature_c: float | None = None
    outdoor_temperature_c: float | None = None
    indoor_humidity_percent: float | None = None
    floor_surface_temperature_c: float | None = None
    supply_temperature_c: float | None = None
    return_temperature_c: float | None = None
    source_in_temperature_c: float | None = None
    source_out_temperature_c: float | None = None
    flow_l_min: float | None = None
    pump_running: bool = False
    valve_open: bool = False
    measured_at: str | None = None


class GeoCoolingDigitalTwin:
    VERSION = "C020.1R1-DIGITAL-TWIN-1.0"
    EXPECTED = (
        "indoor_temperature_c", "outdoor_temperature_c",
        "indoor_humidity_percent", "floor_surface_temperature_c",
        "supply_temperature_c", "return_temperature_c",
        "source_in_temperature_c", "source_out_temperature_c", "flow_l_min",
    )

    def __init__(self, path: str | None = None) -> None:
        base = Path(os.getenv("GEOCOOLING_DATA_DIR", "/app/data/geocooling"))
        self.path = Path(path or os.getenv(
            "GEOCOOLING_DIGITAL_TWIN_PATH",
            str(base / "digital-twin-c020.json"),
        ))
        self._lock = threading.RLock()
        self._state: dict[str, Any] | None = None
        self._load()

    @staticmethod
    def dew_point_c(temperature_c: float | None, humidity_percent: float | None) -> float | None:
        if temperature_c is None or humidity_percent is None:
            return None
        if humidity_percent <= 0 or humidity_percent > 100:
            return None
        a, b = 17.62, 243.12
        gamma = math.log(humidity_percent / 100.0) + (a * temperature_c) / (b + temperature_c)
        return round((b * gamma) / (a - gamma), 2)

    def _load(self) -> None:
        try:
            if self.path.exists():
                payload = json.loads(self.path.read_text(encoding="utf-8"))
                state = payload.get("state")
                if isinstance(state, dict):
                    self._state = state
        except Exception:
            self._state = None

    def _persist(self) -> None:
        if self._state is None:
            return
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
            tmp = self.path.with_suffix(self.path.suffix + ".tmp")
            tmp.write_text(json.dumps({
                "version": self.VERSION,
                "saved_at": utc_now_iso(),
                "state": self._state,
            }, ensure_ascii=False, indent=2), encoding="utf-8")
            tmp.replace(self.path)
        except Exception:
            pass

    def _normalize(self, payload: DigitalTwinInputs | dict[str, Any]) -> DigitalTwinInputs:
        if isinstance(payload, DigitalTwinInputs):
            return payload
        if not isinstance(payload, dict):
            raise TypeError("Digital twin payload must be a dictionary")
        return DigitalTwinInputs(
            indoor_temperature_c=finite_float(payload.get("indoor_temperature_c")),
            upstairs_temperature_c=finite_float(payload.get("upstairs_temperature_c")),
            outdoor_temperature_c=finite_float(payload.get("outdoor_temperature_c")),
            indoor_humidity_percent=finite_float(payload.get("indoor_humidity_percent")),
            floor_surface_temperature_c=finite_float(payload.get("floor_surface_temperature_c")),
            supply_temperature_c=finite_float(payload.get("supply_temperature_c")),
            return_temperature_c=finite_float(payload.get("return_temperature_c")),
            source_in_temperature_c=finite_float(payload.get("source_in_temperature_c")),
            source_out_temperature_c=finite_float(payload.get("source_out_temperature_c")),
            flow_l_min=finite_float(payload.get("flow_l_min")),
            pump_running=bool(payload.get("pump_running", False)),
            valve_open=bool(payload.get("valve_open", False)),
            measured_at=payload.get("measured_at"),
        )

    def update(self, payload: DigitalTwinInputs | dict[str, Any]) -> dict[str, Any]:
        v = self._normalize(payload)
        available = sum(getattr(v, name) is not None for name in self.EXPECTED)
        quality = round(100.0 * available / len(self.EXPECTED), 1)

        slab = v.floor_surface_temperature_c
        if slab is not None and v.indoor_temperature_c is not None:
            slab = round(slab * 0.70 + v.indoor_temperature_c * 0.30, 2)
        elif slab is None:
            vals = [x for x in (v.supply_temperature_c, v.return_temperature_c, v.indoor_temperature_c) if x is not None]
            slab = round(sum(vals) / len(vals), 2) if vals else None

        dew = self.dew_point_c(v.indoor_temperature_c, v.indoor_humidity_percent)
        reference = v.floor_surface_temperature_c if v.floor_surface_temperature_c is not None else v.supply_temperature_c
        margin = round(reference - dew, 2) if reference is not None and dew is not None else None
        if margin is None:
            risk = "UNKNOWN"
        elif margin < 0:
            risk = "CRITICAL"
        elif margin < 1.5:
            risk = "HIGH"
        elif margin < 3:
            risk = "WATCH"
        else:
            risk = "LOW"

        cold_storage = 0.0
        if v.indoor_temperature_c is not None and slab is not None:
            cold_storage = round(clamp((v.indoor_temperature_c - slab) / 5 * 100, 0, 100), 1)

        observations: list[str] = []
        if quality < 50:
            observations.append("INSUFFICIENT_SENSOR_COVERAGE")
        if risk in {"HIGH", "CRITICAL"}:
            observations.append("CONDENSATION_PROTECTION_REQUIRED")
        if v.pump_running and not v.valve_open:
            observations.append("PUMP_VALVE_STATE_INCONSISTENT")
        if v.flow_l_min is not None and v.pump_running and v.flow_l_min <= 0:
            observations.append("PUMP_RUNNING_WITHOUT_FLOW")

        active = bool(v.pump_running and v.valve_open and (v.flow_l_min is None or v.flow_l_min > 0))
        state = {
            "generated_at": v.measured_at or utc_now_iso(),
            "version": self.VERSION,
            "status": "READY" if quality >= 50 else "DEGRADED",
            "confidence_percent": round(clamp(quality * .75 + (20 if v.floor_surface_temperature_c is not None else 8) + (5 if v.indoor_temperature_c is not None else 0), 0, 100), 1),
            "data_quality_percent": quality,
            "indoor_air_temperature_c": v.indoor_temperature_c,
            "upstairs_air_temperature_c": v.upstairs_temperature_c,
            "outdoor_air_temperature_c": v.outdoor_temperature_c,
            "indoor_humidity_percent": v.indoor_humidity_percent,
            "estimated_slab_temperature_c": slab,
            "floor_surface_temperature_c": v.floor_surface_temperature_c,
            "supply_temperature_c": v.supply_temperature_c,
            "return_temperature_c": v.return_temperature_c,
            "source_in_temperature_c": v.source_in_temperature_c,
            "source_out_temperature_c": v.source_out_temperature_c,
            "secondary_delta_t_c": round(v.return_temperature_c - v.supply_temperature_c, 2) if v.return_temperature_c is not None and v.supply_temperature_c is not None else None,
            "source_delta_t_c": round(v.source_out_temperature_c - v.source_in_temperature_c, 2) if v.source_out_temperature_c is not None and v.source_in_temperature_c is not None else None,
            "dew_point_c": dew,
            "condensation_margin_c": margin,
            "condensation_risk": risk,
            "cold_storage_percent": cold_storage,
            "thermal_inertia": "HIGH" if v.indoor_temperature_c is not None and slab is not None and abs(v.indoor_temperature_c - slab) >= 1.5 else "UNKNOWN",
            "thermal_response_minutes": None,
            "thermal_state": "CONDENSATION_LIMITED" if risk in {"HIGH", "CRITICAL"} else ("ACTIVE_COOLING" if active else ("COLD_STORED" if cold_storage >= 70 else "NEUTRAL")),
            "pump_running": v.pump_running,
            "valve_open": v.valve_open,
            "active_cooling": active,
            "observations": observations,
        }
        with self._lock:
            self._state = state
            self._persist()
        return copy.deepcopy(state)

    def status(self) -> dict[str, Any]:
        with self._lock:
            if self._state is None:
                return {
                    "generated_at": utc_now_iso(),
                    "version": self.VERSION,
                    "status": "NOT_INITIALIZED",
                    "confidence_percent": 0.0,
                    "data_quality_percent": 0.0,
                    "hardware_touched": False,
                }
            result = copy.deepcopy(self._state)
            result["hardware_touched"] = False
            return result
