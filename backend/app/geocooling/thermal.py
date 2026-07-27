from __future__ import annotations

import math
import os
import threading
from collections import deque
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from typing import Any

from app.geocooling.adaptive_model import AdaptiveThermalModel


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(slots=True)
class ThermalSnapshot:
    timestamp: datetime
    indoor_temperature_c: float | None = None
    indoor_humidity_percent: float | None = None
    surface_temperature_c: float | None = None
    floor_supply_temperature_c: float | None = None
    floor_return_temperature_c: float | None = None
    source_inlet_temperature_c: float | None = None
    source_outlet_temperature_c: float | None = None
    outdoor_temperature_c: float | None = None
    flow_rate_l_min: float | None = None
    pump_running: bool = False
    valve_open: bool = False

    def as_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["timestamp"] = self.timestamp.isoformat()
        return data


class ThermalEngine:
    """Historique thermique mémoire + indicateurs dérivés GeoCooling."""

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._history: deque[ThermalSnapshot] = deque(
            maxlen=max(100, int(os.getenv("GEOCOOLING_THERMAL_HISTORY_SIZE", "10000")))
        )
        self.default_flow_rate_l_min = max(
            0.0, float(os.getenv("GEOCOOLING_FLOW_RATE_L_MIN", "0"))
        )
        self._energy_kwh = 0.0
        self.adaptive_model = AdaptiveThermalModel()

    @staticmethod
    def _finite_or_none(value: Any, name: str) -> float | None:
        if value is None:
            return None
        number = float(value)
        if not math.isfinite(number):
            raise ValueError(f"{name} invalide")
        return number

    def ingest(self, payload: dict[str, Any]) -> dict[str, Any]:
        raw_ts = payload.get("timestamp")
        if raw_ts:
            timestamp = datetime.fromisoformat(str(raw_ts).replace("Z", "+00:00"))
            if timestamp.tzinfo is None:
                timestamp = timestamp.replace(tzinfo=timezone.utc)
            timestamp = timestamp.astimezone(timezone.utc)
        else:
            timestamp = utc_now()

        snapshot = ThermalSnapshot(
            timestamp=timestamp,
            indoor_temperature_c=self._finite_or_none(payload.get("indoor_temperature_c"), "Température intérieure"),
            indoor_humidity_percent=self._finite_or_none(payload.get("indoor_humidity_percent"), "Humidité intérieure"),
            surface_temperature_c=self._finite_or_none(payload.get("surface_temperature_c"), "Température de surface"),
            floor_supply_temperature_c=self._finite_or_none(payload.get("floor_supply_temperature_c"), "Température départ plancher"),
            floor_return_temperature_c=self._finite_or_none(payload.get("floor_return_temperature_c"), "Température retour plancher"),
            source_inlet_temperature_c=self._finite_or_none(payload.get("source_inlet_temperature_c"), "Température entrée source"),
            source_outlet_temperature_c=self._finite_or_none(payload.get("source_outlet_temperature_c"), "Température sortie source"),
            outdoor_temperature_c=self._finite_or_none(payload.get("outdoor_temperature_c"), "Température extérieure"),
            flow_rate_l_min=self._finite_or_none(payload.get("flow_rate_l_min"), "Débit"),
            pump_running=bool(payload.get("pump_running", False)),
            valve_open=bool(payload.get("valve_open", False)),
        )

        if snapshot.indoor_humidity_percent is not None and not 0 <= snapshot.indoor_humidity_percent <= 100:
            raise ValueError("Humidité intérieure hors plage 0-100 %")
        if snapshot.flow_rate_l_min is not None and snapshot.flow_rate_l_min < 0:
            raise ValueError("Débit négatif interdit")

        with self._lock:
            previous = self._history[-1] if self._history else None
            self._history.append(snapshot)

            if previous is not None:
                dt_h = max(
                    0.0,
                    (
                        snapshot.timestamp
                        - previous.timestamp
                    ).total_seconds()
                    / 3600.0,
                )

                power_kw = self._power_kw(snapshot)

                if dt_h > 0 and power_kw is not None:
                    self._energy_kwh += (
                        max(0.0, power_kw)
                        * dt_h
                    )

                self.adaptive_model.observe(
                    previous=previous,
                    current=snapshot,
                    cooling_power_kw=power_kw,
                )
        return self.metrics()

    def latest(self) -> ThermalSnapshot | None:
        with self._lock:
            return self._history[-1] if self._history else None

    def history(self, limit: int = 200) -> list[dict[str, Any]]:
        safe_limit = min(max(1, limit), 5000)
        with self._lock:
            return [item.as_dict() for item in list(self._history)[-safe_limit:]]

    def _power_kw(self, snapshot: ThermalSnapshot) -> float | None:
        if snapshot.floor_supply_temperature_c is None or snapshot.floor_return_temperature_c is None:
            return None
        flow = snapshot.flow_rate_l_min
        if flow is None or flow <= 0:
            flow = self.default_flow_rate_l_min
        if flow <= 0:
            return None
        delta_t = snapshot.floor_return_temperature_c - snapshot.floor_supply_temperature_c
        # Eau : P(kW) = 0,06977 × débit(l/min) × ΔT(K)
        return round(0.06977 * flow * delta_t, 3)

    def _trend(self, field: str, minutes: int) -> float | None:
        with self._lock:
            if len(self._history) < 2:
                return None
            end = self._history[-1]
            end_value = getattr(end, field)
            if end_value is None:
                return None
            threshold = end.timestamp - timedelta(minutes=minutes)
            start = None
            for item in reversed(self._history):
                value = getattr(item, field)
                if value is not None:
                    start = item
                if item.timestamp <= threshold:
                    break
            if start is None or start is end:
                return None
            elapsed_h = (end.timestamp - start.timestamp).total_seconds() / 3600.0
            if elapsed_h <= 0:
                return None
            start_value = getattr(start, field)
            return round((end_value - start_value) / elapsed_h, 3)

    def metrics(self) -> dict[str, Any]:
        latest = self.latest()
        if latest is None:
            return {
                "available": False,
                "reason": "Aucune mesure thermique reçue",
                "history_count": 0,
                "energy_transferred_kwh": round(self._energy_kwh, 3),
                "adaptive_model": self.adaptive_model.status(),
            }

        floor_delta = None
        if latest.floor_supply_temperature_c is not None and latest.floor_return_temperature_c is not None:
            floor_delta = round(latest.floor_return_temperature_c - latest.floor_supply_temperature_c, 3)

        source_delta = None
        if latest.source_inlet_temperature_c is not None and latest.source_outlet_temperature_c is not None:
            source_delta = round(latest.source_outlet_temperature_c - latest.source_inlet_temperature_c, 3)

        return {
            "available": True,
            "latest": latest.as_dict(),
            "history_count": len(self._history),
            "floor_delta_t_c": floor_delta,
            "source_delta_t_c": source_delta,
            "cooling_power_kw": self._power_kw(latest),
            "energy_transferred_kwh": round(self._energy_kwh, 3),
            "trends_c_per_hour": {
                "indoor_5m": self._trend("indoor_temperature_c", 5),
                "indoor_30m": self._trend("indoor_temperature_c", 30),
                "indoor_120m": self._trend("indoor_temperature_c", 120),
                "surface_30m": self._trend("surface_temperature_c", 30),
                "outdoor_30m": self._trend("outdoor_temperature_c", 30),
            },
            "adaptive_model": self.adaptive_model.status(),
            "configuration": {
                "default_flow_rate_l_min": self.default_flow_rate_l_min,
                "history_capacity": self._history.maxlen,
            },
        }
