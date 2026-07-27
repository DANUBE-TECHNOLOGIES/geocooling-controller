import math
import os
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class SafetyDecision:
    safe: bool
    level: str
    reason: str
    dew_point_c: float | None = None
    surface_temperature_c: float | None = None
    margin_c: float | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "safe": self.safe,
            "level": self.level,
            "reason": self.reason,
            "dew_point_c": self.dew_point_c,
            "surface_temperature_c": self.surface_temperature_c,
            "margin_c": self.margin_c,
        }


class GeoCoolingSafetyManager:
    """Contrôles thermiques anti-condensation du GeoCooling."""

    def __init__(self) -> None:
        self.minimum_margin_c = max(
            0.5,
            float(os.getenv("GEOCOOLING_MIN_DEW_POINT_MARGIN_C", "3.0")),
        )
        self.require_thermal_sensors = os.getenv(
            "GEOCOOLING_REQUIRE_THERMAL_SENSORS", "false"
        ).strip().lower() in {"1", "true", "yes", "on"}

    @staticmethod
    def dew_point_c(temperature_c: float, humidity_percent: float) -> float:
        if not math.isfinite(temperature_c):
            raise ValueError("Température intérieure invalide")
        if not math.isfinite(humidity_percent) or not 0 < humidity_percent <= 100:
            raise ValueError("Humidité intérieure invalide")

        a = 17.62
        b = 243.12
        gamma = math.log(humidity_percent / 100.0) + (
            a * temperature_c / (b + temperature_c)
        )
        return b * gamma / (a - gamma)

    def evaluate(
        self,
        *,
        indoor_temperature_c: float | None,
        indoor_humidity_percent: float | None,
        surface_temperature_c: float | None,
    ) -> SafetyDecision:
        values = (
            indoor_temperature_c,
            indoor_humidity_percent,
            surface_temperature_c,
        )
        if any(value is None for value in values):
            if self.require_thermal_sensors:
                return SafetyDecision(
                    safe=False,
                    level="blocked",
                    reason="Capteurs thermiques requis mais données incomplètes",
                )
            return SafetyDecision(
                safe=True,
                level="unavailable",
                reason="Données thermiques incomplètes, contrôle non bloquant",
            )

        try:
            indoor = float(indoor_temperature_c)
            humidity = float(indoor_humidity_percent)
            surface = float(surface_temperature_c)
            if not math.isfinite(surface):
                raise ValueError("Température de surface invalide")
            dew_point = self.dew_point_c(indoor, humidity)
        except (TypeError, ValueError) as exc:
            return SafetyDecision(
                safe=False,
                level="invalid",
                reason=str(exc),
            )

        margin = surface - dew_point
        safe = margin >= self.minimum_margin_c
        return SafetyDecision(
            safe=safe,
            level="safe" if safe else "condensation_risk",
            reason=(
                "Marge anti-condensation suffisante"
                if safe
                else "Marge anti-condensation insuffisante"
            ),
            dew_point_c=round(dew_point, 2),
            surface_temperature_c=round(surface, 2),
            margin_c=round(margin, 2),
        )
