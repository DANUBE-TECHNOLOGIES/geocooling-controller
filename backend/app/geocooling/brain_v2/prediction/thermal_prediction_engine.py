from __future__ import annotations

import json
import math
import os

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any, Literal


Scenario = Literal[
    "auto",
    "passive",
    "cooling",
]


@dataclass(frozen=True)
class PredictionConfiguration:
    target_temperature_c: float = 24.0
    horizon_minutes: int = 360
    step_minutes: int = 15


class ThermalPredictionEngine:
    VERSION = "C022.4-THERMAL-PREDICTION-1.0"

    def __init__(
        self,
        data_directory: str | Path | None = None,
    ) -> None:
        configured_directory = (
            data_directory
            or os.getenv(
                "GEOCOOLING_BRAIN_V2_DATA_DIR",
                "/app/data/geocooling/brain_v2",
            )
        )

        self.data_directory = Path(
            configured_directory
        )

        self.model_path = (
            self.data_directory
            / "thermal-learning.json"
        )

        self.observations_path = (
            self.data_directory
            / "observations.jsonl"
        )

    @staticmethod
    def _utc_now() -> datetime:
        return datetime.now(
            timezone.utc
        )

    @staticmethod
    def _as_float(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        if isinstance(value, dict):
            preferred_keys = (
                "value",
                "mean",
                "average",
                "rate",
                "estimate",
                "estimated_value",
                "kw",
                "c_per_hour",
            )

            for key in preferred_keys:
                if key in value:
                    converted = (
                        ThermalPredictionEngine._as_float(
                            value[key]
                        )
                    )

                    if converted is not None:
                        return converted

            for child in value.values():
                converted = (
                    ThermalPredictionEngine._as_float(
                        child
                    )
                )

                if converted is not None:
                    return converted

            return None

        if isinstance(value, str):
            cleaned = (
                value.strip()
                .replace(",", ".")
                .replace("°C/h", "")
                .replace("°C", "")
                .replace("%", "")
                .replace("kW", "")
            )

            try:
                value = float(cleaned)
            except ValueError:
                return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(result):
            return None

        return result

    @staticmethod
    def _clamp(
        value: float,
        minimum: float,
        maximum: float,
    ) -> float:
        return max(
            minimum,
            min(
                maximum,
                value,
            ),
        )

    def _read_json(
        self,
        path: Path,
    ) -> dict[str, Any]:
        if not path.exists():
            return {}

        try:
            payload = json.loads(
                path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return {}

        if not isinstance(payload, dict):
            return {}

        return payload

    def _read_observations(
        self,
        limit: int = 288,
    ) -> list[dict[str, Any]]:
        if not self.observations_path.exists():
            return []

        observations: list[
            dict[str, Any]
        ] = []

        try:
            lines = (
                self.observations_path
                .read_text(
                    encoding="utf-8"
                )
                .splitlines()
            )
        except OSError:
            return []

        for line in lines[-limit:]:
            if not line.strip():
                continue

            try:
                payload = json.loads(
                    line
                )
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                observations.append(
                    payload
                )

        return observations

    @staticmethod
    def _parse_timestamp(
        value: Any,
    ) -> datetime | None:
        if not isinstance(value, str):
            return None

        normalized = value.strip()

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                normalized
            )
        except ValueError:
            return None

        if parsed.tzinfo is None:
            parsed = parsed.replace(
                tzinfo=timezone.utc
            )

        return parsed.astimezone(
            timezone.utc
        )

    def _latest_observation(
        self,
        observations: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any]:
        if not observations:
            return {}

        return observations[-1]

    def _observation_value(
        self,
        observation: dict[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key in observation:
                value = self._as_float(
                    observation[key]
                )

                if value is not None:
                    return value

        return None

    def _model_value(
        self,
        model: dict[str, Any],
        *keys: str,
    ) -> float | None:
        for key in keys:
            if key in model:
                value = self._as_float(
                    model[key]
                )

                if value is not None:
                    return value

        nested_candidates = (
            model.get("parameters"),
            model.get("metrics"),
            model.get("model"),
            model.get("thermal_model"),
        )

        for candidate in nested_candidates:
            if not isinstance(
                candidate,
                dict,
            ):
                continue

            for key in keys:
                if key in candidate:
                    value = self._as_float(
                        candidate[key]
                    )

                    if value is not None:
                        return value

        return None

    def _observed_rate(
        self,
        observations: list[
            dict[str, Any]
        ],
        cooling: bool,
    ) -> float | None:
        rates: list[float] = []

        for previous, current in zip(
            observations,
            observations[1:],
        ):
            previous_temperature = (
                self._observation_value(
                    previous,
                    "indoor_temperature_c",
                    "indoor_temperature",
                )
            )

            current_temperature = (
                self._observation_value(
                    current,
                    "indoor_temperature_c",
                    "indoor_temperature",
                )
            )

            previous_time = (
                self._parse_timestamp(
                    previous.get(
                        "timestamp"
                    )
                )
            )

            current_time = (
                self._parse_timestamp(
                    current.get(
                        "timestamp"
                    )
                )
            )

            if (
                previous_temperature is None
                or current_temperature is None
                or previous_time is None
                or current_time is None
            ):
                continue

            duration_hours = (
                current_time
                - previous_time
            ).total_seconds() / 3600.0

            if (
                duration_hours <= 0
                or duration_hours > 3
            ):
                continue

            active_cooling = bool(
                current.get(
                    "active_cooling",
                    False,
                )
            )

            if active_cooling != cooling:
                continue

            rate = (
                current_temperature
                - previous_temperature
            ) / duration_hours

            if -5.0 <= rate <= 5.0:
                rates.append(
                    rate
                )

        if not rates:
            return None

        rates.sort()

        middle = len(rates) // 2

        if len(rates) % 2:
            return rates[middle]

        return (
            rates[middle - 1]
            + rates[middle]
        ) / 2.0

    def _resolve_rates(
        self,
        model: dict[str, Any],
        observations: list[
            dict[str, Any]
        ],
    ) -> dict[str, Any]:
        cooling_rate = self._model_value(
            model,
            "building_cooling_rate",
            "cooling_rate_c_per_hour",
        )

        passive_rate = self._model_value(
            model,
            "building_passive_warming_rate",
            "passive_warming_rate_c_per_hour",
        )

        cooling_source = "learned_model"
        passive_source = "learned_model"

        if cooling_rate is None:
            cooling_rate = self._observed_rate(
                observations,
                cooling=True,
            )

            cooling_source = (
                "recent_observations"
            )

        if passive_rate is None:
            passive_rate = self._observed_rate(
                observations,
                cooling=False,
            )

            passive_source = (
                "recent_observations"
            )

        if cooling_rate is None:
            cooling_rate = -0.20
            cooling_source = (
                "conservative_fallback"
            )

        if passive_rate is None:
            passive_rate = 0.08
            passive_source = (
                "conservative_fallback"
            )

        cooling_rate = -abs(
            self._clamp(
                cooling_rate,
                -2.0,
                2.0,
            )
        )

        passive_rate = abs(
            self._clamp(
                passive_rate,
                -2.0,
                2.0,
            )
        )

        return {
            "cooling_rate_c_per_hour": round(
                cooling_rate,
                4,
            ),
            "passive_rate_c_per_hour": round(
                passive_rate,
                4,
            ),
            "cooling_rate_source": (
                cooling_source
            ),
            "passive_rate_source": (
                passive_source
            ),
        }

    def _confidence(
        self,
        model: dict[str, Any],
        observations: list[
            dict[str, Any]
        ],
        rates: dict[str, Any],
    ) -> float:
        confidence = self._model_value(
            model,
            "global_confidence_percent",
            "confidence_percent",
            "confidence",
        )

        if confidence is None:
            confidence = 0.0

        if 0.0 <= confidence <= 1.0:
            confidence *= 100.0

        observation_bonus = min(
            len(observations) * 0.35,
            20.0,
        )

        source_bonus = 0.0

        if (
            rates[
                "cooling_rate_source"
            ]
            == "learned_model"
        ):
            source_bonus += 10.0

        if (
            rates[
                "passive_rate_source"
            ]
            == "learned_model"
        ):
            source_bonus += 10.0

        result = max(
            confidence,
            observation_bonus
            + source_bonus,
        )

        return round(
            self._clamp(
                result,
                0.0,
                100.0,
            ),
            1,
        )

    @staticmethod
    def _scenario_rate(
        scenario: Scenario,
        latest: dict[str, Any],
        rates: dict[str, Any],
    ) -> tuple[str, float]:
        selected_scenario = scenario

        if scenario == "auto":
            active = bool(
                latest.get(
                    "active_cooling",
                    False,
                )
            )

            selected_scenario = (
                "cooling"
                if active
                else "passive"
            )

        if selected_scenario == "cooling":
            return (
                selected_scenario,
                float(
                    rates[
                        "cooling_rate_c_per_hour"
                    ]
                ),
            )

        return (
            selected_scenario,
            float(
                rates[
                    "passive_rate_c_per_hour"
                ]
            ),
        )

    @staticmethod
    def _minutes_to_target(
        current_temperature_c: float,
        target_temperature_c: float,
        rate_c_per_hour: float,
    ) -> int | None:
        delta = (
            target_temperature_c
            - current_temperature_c
        )

        if abs(delta) < 0.01:
            return 0

        if abs(rate_c_per_hour) < 0.0001:
            return None

        duration_hours = (
            delta
            / rate_c_per_hour
        )

        if duration_hours < 0:
            return None

        return int(
            round(
                duration_hours * 60.0
            )
        )

    def forecast(
        self,
        scenario: Scenario = "auto",
        target_temperature_c: float = 24.0,
        horizon_minutes: int = 360,
        step_minutes: int = 15,
    ) -> dict[str, Any]:
        horizon_minutes = int(
            self._clamp(
                float(horizon_minutes),
                15.0,
                1440.0,
            )
        )

        step_minutes = int(
            self._clamp(
                float(step_minutes),
                5.0,
                120.0,
            )
        )

        target_temperature_c = (
            self._clamp(
                float(
                    target_temperature_c
                ),
                15.0,
                35.0,
            )
        )

        model = self._read_json(
            self.model_path
        )

        observations = (
            self._read_observations()
        )

        latest = self._latest_observation(
            observations
        )

        current_temperature = (
            self._observation_value(
                latest,
                "indoor_temperature_c",
                "indoor_temperature",
            )
        )

        if current_temperature is None:
            raise ValueError(
                "Aucune température intérieure exploitable"
            )

        outdoor_temperature = (
            self._observation_value(
                latest,
                "outdoor_temperature_c",
                "outdoor_temperature",
            )
        )

        rates = self._resolve_rates(
            model,
            observations,
        )

        selected_scenario, base_rate = (
            self._scenario_rate(
                scenario,
                latest,
                rates,
            )
        )

        confidence = self._confidence(
            model,
            observations,
            rates,
        )

        generated_at = self._utc_now()

        points: list[
            dict[str, Any]
        ] = []

        predicted_temperature = (
            current_temperature
        )

        elapsed_minutes = 0

        while elapsed_minutes <= horizon_minutes:
            timestamp = (
                generated_at
                + timedelta(
                    minutes=elapsed_minutes
                )
            )

            points.append(
                {
                    "timestamp": (
                        timestamp.isoformat()
                    ),
                    "elapsed_minutes": (
                        elapsed_minutes
                    ),
                    "temperature_c": round(
                        predicted_temperature,
                        2,
                    ),
                }
            )

            if elapsed_minutes >= horizon_minutes:
                break

            interval_minutes = min(
                step_minutes,
                horizon_minutes
                - elapsed_minutes,
            )

            interval_hours = (
                interval_minutes
                / 60.0
            )

            dynamic_rate = base_rate

            if (
                selected_scenario
                == "passive"
                and outdoor_temperature
                is not None
            ):
                thermal_gap = (
                    outdoor_temperature
                    - predicted_temperature
                )

                gap_factor = self._clamp(
                    abs(thermal_gap) / 8.0,
                    0.25,
                    1.75,
                )

                dynamic_rate = (
                    abs(base_rate)
                    * gap_factor
                    * (
                        1.0
                        if thermal_gap >= 0
                        else -1.0
                    )
                )

            predicted_temperature += (
                dynamic_rate
                * interval_hours
            )

            predicted_temperature = (
                self._clamp(
                    predicted_temperature,
                    5.0,
                    45.0,
                )
            )

            elapsed_minutes += (
                interval_minutes
            )

        minutes_to_target = (
            self._minutes_to_target(
                current_temperature,
                target_temperature_c,
                base_rate,
            )
        )

        target_reached_in_horizon = any(
            (
                point["temperature_c"]
                <= target_temperature_c
            )
            if current_temperature
            > target_temperature_c
            else (
                point["temperature_c"]
                >= target_temperature_c
            )
            for point in points
        )

        status = "READY"

        if confidence < 20.0:
            status = "LIMITED"

        elif confidence < 60.0:
            status = "LEARNING"

        return {
            "version": self.VERSION,
            "status": status,
            "generated_at": (
                generated_at.isoformat()
            ),
            "scenario_requested": scenario,
            "scenario_applied": (
                selected_scenario
            ),
            "current_temperature_c": round(
                current_temperature,
                2,
            ),
            "outdoor_temperature_c": (
                round(
                    outdoor_temperature,
                    2,
                )
                if outdoor_temperature
                is not None
                else None
            ),
            "target_temperature_c": round(
                target_temperature_c,
                2,
            ),
            "horizon_minutes": (
                horizon_minutes
            ),
            "step_minutes": step_minutes,
            "applied_rate_c_per_hour": round(
                base_rate,
                4,
            ),
            "cooling_rate_c_per_hour": (
                rates[
                    "cooling_rate_c_per_hour"
                ]
            ),
            "passive_rate_c_per_hour": (
                rates[
                    "passive_rate_c_per_hour"
                ]
            ),
            "rate_sources": {
                "cooling": (
                    rates[
                        "cooling_rate_source"
                    ]
                ),
                "passive": (
                    rates[
                        "passive_rate_source"
                    ]
                ),
            },
            "minutes_to_target": (
                minutes_to_target
            ),
            "target_reached_in_horizon": (
                target_reached_in_horizon
            ),
            "predicted_temperature_at_horizon_c": (
                points[-1][
                    "temperature_c"
                ]
            ),
            "global_confidence_percent": (
                confidence
            ),
            "observations_used": len(
                observations
            ),
            "forecast": points,
            "safety": {
                "advisory_only": True,
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
            },
        }

    def compare(
        self,
        target_temperature_c: float = 24.0,
        horizon_minutes: int = 360,
        step_minutes: int = 15,
    ) -> dict[str, Any]:
        passive = self.forecast(
            scenario="passive",
            target_temperature_c=(
                target_temperature_c
            ),
            horizon_minutes=(
                horizon_minutes
            ),
            step_minutes=step_minutes,
        )

        cooling = self.forecast(
            scenario="cooling",
            target_temperature_c=(
                target_temperature_c
            ),
            horizon_minutes=(
                horizon_minutes
            ),
            step_minutes=step_minutes,
        )

        passive_final = float(
            passive[
                "predicted_temperature_at_horizon_c"
            ]
        )

        cooling_final = float(
            cooling[
                "predicted_temperature_at_horizon_c"
            ]
        )

        thermal_gain = (
            passive_final
            - cooling_final
        )

        recommendation = (
            "COOLING_BENEFICIAL"
            if thermal_gain >= 0.3
            else "LIMITED_DIFFERENCE"
        )

        return {
            "version": self.VERSION,
            "status": (
                cooling["status"]
            ),
            "generated_at": (
                cooling[
                    "generated_at"
                ]
            ),
            "target_temperature_c": (
                target_temperature_c
            ),
            "horizon_minutes": (
                horizon_minutes
            ),
            "passive": passive,
            "cooling": cooling,
            "cooling_benefit_at_horizon_c": round(
                thermal_gain,
                2,
            ),
            "advisory_recommendation": (
                recommendation
            ),
            "global_confidence_percent": (
                min(
                    passive[
                        "global_confidence_percent"
                    ],
                    cooling[
                        "global_confidence_percent"
                    ],
                )
            ),
            "safety": {
                "advisory_only": True,
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
            },
        }

    def status(
        self,
    ) -> dict[str, Any]:
        model = self._read_json(
            self.model_path
        )

        observations = (
            self._read_observations()
        )

        latest = self._latest_observation(
            observations
        )

        current_temperature = (
            self._observation_value(
                latest,
                "indoor_temperature_c",
                "indoor_temperature",
            )
        )

        rates = self._resolve_rates(
            model,
            observations,
        )

        confidence = self._confidence(
            model,
            observations,
            rates,
        )

        if current_temperature is None:
            state = "COLLECTING"

        elif confidence < 20.0:
            state = "LIMITED"

        elif confidence < 60.0:
            state = "LEARNING"

        else:
            state = "READY"

        return {
            "version": self.VERSION,
            "status": state,
            "model_path": str(
                self.model_path
            ),
            "model_exists": (
                self.model_path.exists()
            ),
            "observations_path": str(
                self.observations_path
            ),
            "observations_exists": (
                self.observations_path.exists()
            ),
            "observations_available": len(
                observations
            ),
            "current_temperature_available": (
                current_temperature
                is not None
            ),
            "current_temperature_c": (
                round(
                    current_temperature,
                    2,
                )
                if current_temperature
                is not None
                else None
            ),
            "cooling_rate_c_per_hour": (
                rates[
                    "cooling_rate_c_per_hour"
                ]
            ),
            "passive_rate_c_per_hour": (
                rates[
                    "passive_rate_c_per_hour"
                ]
            ),
            "rate_sources": {
                "cooling": (
                    rates[
                        "cooling_rate_source"
                    ]
                ),
                "passive": (
                    rates[
                        "passive_rate_source"
                    ]
                ),
            },
            "global_confidence_percent": (
                confidence
            ),
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "data_directory_writable": (
                os.access(
                    self.data_directory,
                    os.W_OK,
                )
            ),
        }
