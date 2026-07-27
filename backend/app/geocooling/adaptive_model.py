from __future__ import annotations

import math
import os
import threading
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True, slots=True)
class AdaptiveThermalEstimate:
    available: bool
    confidence: int
    passive_sample_count: int
    active_sample_count: int
    total_sample_count: int

    passive_exchange_rate_per_hour: float | None
    natural_temperature_rate_c_per_hour: float | None
    active_cooling_rate_c_per_hour: float | None
    house_thermal_capacity_kwh_per_c: float | None

    building_inertia_index: int | None
    building_inertia_class: str

    last_observation_at: str | None
    reason: str

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


class AdaptiveThermalModel:
    """
    Modèle thermique adaptatif du bâtiment.

    Le modèle apprend à partir de deux mesures successives :

    - pompe arrêtée :
      apprentissage de l'échange thermique naturel avec l'extérieur ;

    - pompe en marche :
      apprentissage de l'effet frigorifique réel et de la capacité
      thermique apparente du bâtiment.

    Il n'effectue aucune commande matérielle.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()

        self.minimum_observation_seconds = max(
            30.0,
            float(
                os.getenv(
                    "GEOCOOLING_LEARNING_MIN_OBSERVATION_SECONDS",
                    "120",
                )
            ),
        )

        self.maximum_observation_seconds = max(
            self.minimum_observation_seconds,
            float(
                os.getenv(
                    "GEOCOOLING_LEARNING_MAX_OBSERVATION_SECONDS",
                    "3600",
                )
            ),
        )

        self.minimum_outdoor_delta_c = max(
            0.5,
            float(
                os.getenv(
                    "GEOCOOLING_LEARNING_MIN_OUTDOOR_DELTA_C",
                    "2.0",
                )
            ),
        )

        self.minimum_active_cooling_rate = max(
            0.01,
            float(
                os.getenv(
                    "GEOCOOLING_LEARNING_MIN_COOLING_RATE_C_PER_H",
                    "0.03",
                )
            ),
        )

        self.alpha = min(
            1.0,
            max(
                0.01,
                float(
                    os.getenv(
                        "GEOCOOLING_LEARNING_ALPHA",
                        "0.15",
                    )
                ),
            ),
        )

        self.default_capacity_kwh_per_c = max(
            0.5,
            float(
                os.getenv(
                    "GEOCOOLING_HOUSE_THERMAL_CAPACITY_KWH_PER_C",
                    "18.0",
                )
            ),
        )

        self.default_passive_exchange_rate = max(
            0.0,
            float(
                os.getenv(
                    "GEOCOOLING_PASSIVE_EXCHANGE_RATE_PER_HOUR",
                    "0.08",
                )
            ),
        )

        self._passive_exchange_rate: float | None = None
        self._natural_temperature_rate: float | None = None
        self._active_cooling_rate: float | None = None
        self._thermal_capacity: float | None = None

        self._passive_samples = 0
        self._active_samples = 0
        self._rejected_samples = 0
        self._last_observation_at: datetime | None = None

    @staticmethod
    def _finite(value: Any) -> float | None:
        if value is None:
            return None

        try:
            number = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(number):
            return None

        return number

    def _ewma(
        self,
        current: float | None,
        observation: float,
    ) -> float:
        if current is None:
            return observation

        return (
            current * (1.0 - self.alpha)
            + observation * self.alpha
        )

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(minimum, min(maximum, value))

    def observe(
        self,
        *,
        previous: Any,
        current: Any,
        cooling_power_kw: float | None,
    ) -> bool:
        """
        Analyse deux snapshots successifs.

        Retourne True lorsqu'un échantillon utile a été accepté.
        """

        previous_indoor = self._finite(
            getattr(
                previous,
                "indoor_temperature_c",
                None,
            )
        )
        current_indoor = self._finite(
            getattr(
                current,
                "indoor_temperature_c",
                None,
            )
        )

        if (
            previous_indoor is None
            or current_indoor is None
        ):
            return False

        previous_timestamp = getattr(
            previous,
            "timestamp",
            None,
        )
        current_timestamp = getattr(
            current,
            "timestamp",
            None,
        )

        if (
            previous_timestamp is None
            or current_timestamp is None
        ):
            return False

        elapsed_seconds = (
            current_timestamp
            - previous_timestamp
        ).total_seconds()

        if (
            elapsed_seconds
            < self.minimum_observation_seconds
            or elapsed_seconds
            > self.maximum_observation_seconds
        ):
            with self._lock:
                self._rejected_samples += 1

            return False

        elapsed_hours = elapsed_seconds / 3600.0
        observed_rate = (
            current_indoor
            - previous_indoor
        ) / elapsed_hours

        if abs(observed_rate) > 5.0:
            with self._lock:
                self._rejected_samples += 1

            return False

        previous_running = bool(
            getattr(previous, "pump_running", False)
        )
        current_running = bool(
            getattr(current, "pump_running", False)
        )

        # On écarte les transitions ON/OFF :
        # elles ne représentent pas un régime thermique stable.
        if previous_running != current_running:
            with self._lock:
                self._rejected_samples += 1

            return False

        previous_outdoor = self._finite(
            getattr(
                previous,
                "outdoor_temperature_c",
                None,
            )
        )
        current_outdoor = self._finite(
            getattr(
                current,
                "outdoor_temperature_c",
                None,
            )
        )

        outdoor = None

        if (
            previous_outdoor is not None
            and current_outdoor is not None
        ):
            outdoor = (
                previous_outdoor
                + current_outdoor
            ) / 2.0
        elif current_outdoor is not None:
            outdoor = current_outdoor
        elif previous_outdoor is not None:
            outdoor = previous_outdoor

        mean_indoor = (
            previous_indoor
            + current_indoor
        ) / 2.0

        accepted = False

        with self._lock:
            if not current_running:
                self._natural_temperature_rate = self._ewma(
                    self._natural_temperature_rate,
                    observed_rate,
                )

                if outdoor is not None:
                    temperature_delta = (
                        outdoor
                        - mean_indoor
                    )

                    if (
                        abs(temperature_delta)
                        >= self.minimum_outdoor_delta_c
                    ):
                        exchange_rate = (
                            observed_rate
                            / temperature_delta
                        )

                        if 0.0 <= exchange_rate <= 1.0:
                            self._passive_exchange_rate = (
                                self._ewma(
                                    self._passive_exchange_rate,
                                    exchange_rate,
                                )
                            )

                self._passive_samples += 1
                accepted = True

            else:
                power = self._finite(
                    cooling_power_kw
                )

                passive_rate = 0.0

                if outdoor is not None:
                    exchange = (
                        self._passive_exchange_rate
                        if self._passive_exchange_rate
                        is not None
                        else self.default_passive_exchange_rate
                    )

                    passive_rate = (
                        outdoor
                        - mean_indoor
                    ) * exchange

                cooling_rate = (
                    passive_rate
                    - observed_rate
                )

                if cooling_rate > 0.0:
                    cooling_rate = self._clamp(
                        cooling_rate,
                        0.0,
                        5.0,
                    )

                    self._active_cooling_rate = (
                        self._ewma(
                            self._active_cooling_rate,
                            cooling_rate,
                        )
                    )

                    if (
                        power is not None
                        and power > 0.0
                        and cooling_rate
                        >= self.minimum_active_cooling_rate
                    ):
                        capacity = (
                            power
                            / cooling_rate
                        )

                        if 0.5 <= capacity <= 250.0:
                            self._thermal_capacity = (
                                self._ewma(
                                    self._thermal_capacity,
                                    capacity,
                                )
                            )

                    self._active_samples += 1
                    accepted = True
                else:
                    self._rejected_samples += 1

            if accepted:
                self._last_observation_at = (
                    current_timestamp.astimezone(
                        timezone.utc
                    )
                    if current_timestamp.tzinfo
                    else current_timestamp.replace(
                        tzinfo=timezone.utc
                    )
                )

        return accepted

    def estimate(self) -> AdaptiveThermalEstimate:
        with self._lock:
            passive_samples = self._passive_samples
            active_samples = self._active_samples
            total_samples = (
                passive_samples
                + active_samples
            )

            passive_confidence = min(
                40,
                passive_samples * 4,
            )
            active_confidence = min(
                45,
                active_samples * 5,
            )
            diversity_bonus = (
                15
                if passive_samples >= 3
                and active_samples >= 3
                else 0
            )

            confidence = min(
                100,
                passive_confidence
                + active_confidence
                + diversity_bonus,
            )

            available = (
                total_samples >= 3
                and (
                    self._passive_exchange_rate
                    is not None
                    or self._active_cooling_rate
                    is not None
                )
            )

            capacity = self._thermal_capacity

            inertia_index: int | None = None
            inertia_class = "UNKNOWN"

            if capacity is not None:
                inertia_index = int(
                    round(
                        self._clamp(
                            capacity
                            / 40.0
                            * 100.0,
                            0.0,
                            100.0,
                        )
                    )
                )

                if inertia_index < 30:
                    inertia_class = "LOW"
                elif inertia_index < 65:
                    inertia_class = "MEDIUM"
                else:
                    inertia_class = "HIGH"

            if not available:
                reason = (
                    "Apprentissage en cours : historique "
                    "thermique encore insuffisant"
                )
            elif confidence < 60:
                reason = (
                    "Modèle disponible avec confiance limitée"
                )
            else:
                reason = (
                    "Modèle thermique adaptatif exploitable"
                )

            return AdaptiveThermalEstimate(
                available=available,
                confidence=confidence,
                passive_sample_count=passive_samples,
                active_sample_count=active_samples,
                total_sample_count=total_samples,
                passive_exchange_rate_per_hour=(
                    round(
                        self._passive_exchange_rate,
                        5,
                    )
                    if self._passive_exchange_rate
                    is not None
                    else None
                ),
                natural_temperature_rate_c_per_hour=(
                    round(
                        self._natural_temperature_rate,
                        4,
                    )
                    if self._natural_temperature_rate
                    is not None
                    else None
                ),
                active_cooling_rate_c_per_hour=(
                    round(
                        self._active_cooling_rate,
                        4,
                    )
                    if self._active_cooling_rate
                    is not None
                    else None
                ),
                house_thermal_capacity_kwh_per_c=(
                    round(capacity, 3)
                    if capacity is not None
                    else None
                ),
                building_inertia_index=inertia_index,
                building_inertia_class=inertia_class,
                last_observation_at=(
                    self._last_observation_at.isoformat()
                    if self._last_observation_at
                    else None
                ),
                reason=reason,
            )

    def status(self) -> dict[str, Any]:
        payload = self.estimate().as_dict()

        payload["configuration"] = {
            "minimum_observation_seconds":
                self.minimum_observation_seconds,
            "maximum_observation_seconds":
                self.maximum_observation_seconds,
            "minimum_outdoor_delta_c":
                self.minimum_outdoor_delta_c,
            "learning_alpha":
                self.alpha,
            "default_capacity_kwh_per_c":
                self.default_capacity_kwh_per_c,
            "default_passive_exchange_rate_per_hour":
                self.default_passive_exchange_rate,
        }

        with self._lock:
            payload["rejected_sample_count"] = (
                self._rejected_samples
            )

        return payload
