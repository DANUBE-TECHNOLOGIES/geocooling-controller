from __future__ import annotations

import json
import math
import os
import statistics
import tempfile

from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

from app.geocooling.brain_v2.models.thermal_learning_model import (
    LearnedMetric,
    ThermalLearningModel,
)


WATER_POWER_FACTOR = 0.0697666667


@dataclass(slots=True)
class NormalizedObservation:
    timestamp: datetime
    indoor_temperature_c: float | None
    outdoor_temperature_c: float | None
    floor_surface_temperature_c: float | None
    floor_supply_temperature_c: float | None
    floor_return_temperature_c: float | None
    source_inlet_temperature_c: float | None
    source_outlet_temperature_c: float | None
    flow_rate_l_min: float | None
    pump_running: bool
    valve_open: bool
    active_cooling: bool
    source: str
    metadata: dict[str, Any]


class ThermalLearningEngine:
    VERSION = "C022.2-THERMAL-LEARNING-1.0"

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

        self.observations_path = (
            self.data_directory
            / "observations.jsonl"
        )

        self.model_path = (
            self.data_directory
            / "thermal-learning.json"
        )

        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

    @staticmethod
    def _float(
        value: Any,
    ) -> float | None:
        if value is None:
            return None

        if isinstance(value, bool):
            return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if not math.isfinite(result):
            return None

        return result

    @staticmethod
    def _bool(
        value: Any,
    ) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return value != 0

        if isinstance(value, str):
            return value.strip().lower() in {
                "1",
                "true",
                "yes",
                "on",
                "active",
                "running",
                "open",
            }

        return False

    @staticmethod
    def _timestamp(
        payload: dict[str, Any],
    ) -> datetime | None:
        candidates = (
            payload.get("timestamp"),
            payload.get("observed_at"),
            payload.get("created_at"),
            payload.get("recorded_at"),
        )

        for candidate in candidates:
            if candidate is None:
                continue

            if isinstance(candidate, (int, float)):
                try:
                    return datetime.fromtimestamp(
                        float(candidate),
                        tz=timezone.utc,
                    )
                except (
                    OverflowError,
                    OSError,
                    ValueError,
                ):
                    continue

            if not isinstance(candidate, str):
                continue

            value = candidate.strip()

            if not value:
                continue

            if value.endswith("Z"):
                value = value[:-1] + "+00:00"

            try:
                parsed = datetime.fromisoformat(value)
            except ValueError:
                continue

            if parsed.tzinfo is None:
                parsed = parsed.replace(
                    tzinfo=timezone.utc
                )
            else:
                parsed = parsed.astimezone(
                    timezone.utc
                )

            return parsed

        return None

    @staticmethod
    def _pick(
        payload: dict[str, Any],
        *keys: str,
    ) -> Any:
        for key in keys:
            if key in payload:
                return payload[key]

        return None

    def _normalize(
        self,
        payload: dict[str, Any],
    ) -> NormalizedObservation | None:
        timestamp = self._timestamp(payload)

        if timestamp is None:
            return None

        metadata = payload.get("metadata")

        if not isinstance(metadata, dict):
            metadata = {}

        return NormalizedObservation(
            timestamp=timestamp,
            indoor_temperature_c=self._float(
                self._pick(
                    payload,
                    "indoor_temperature_c",
                    "indoor_temperature",
                    "temperature_indoor_c",
                )
            ),
            outdoor_temperature_c=self._float(
                self._pick(
                    payload,
                    "outdoor_temperature_c",
                    "outdoor_temperature",
                    "temperature_outdoor_c",
                )
            ),
            floor_surface_temperature_c=self._float(
                self._pick(
                    payload,
                    "floor_surface_temperature_c",
                    "surface_temperature_c",
                    "floor_surface_c",
                )
            ),
            floor_supply_temperature_c=self._float(
                self._pick(
                    payload,
                    "floor_supply_temperature_c",
                    "supply_temperature_c",
                    "floor_departure_temperature_c",
                )
            ),
            floor_return_temperature_c=self._float(
                self._pick(
                    payload,
                    "floor_return_temperature_c",
                    "return_temperature_c",
                )
            ),
            source_inlet_temperature_c=self._float(
                self._pick(
                    payload,
                    "source_inlet_temperature_c",
                    "source_in_temperature_c",
                )
            ),
            source_outlet_temperature_c=self._float(
                self._pick(
                    payload,
                    "source_outlet_temperature_c",
                    "source_out_temperature_c",
                )
            ),
            flow_rate_l_min=self._float(
                self._pick(
                    payload,
                    "flow_rate_l_min",
                    "flow_l_min",
                    "hydraulic_flow_l_min",
                )
            ),
            pump_running=self._bool(
                self._pick(
                    payload,
                    "pump_running",
                    "pump",
                )
            ),
            valve_open=self._bool(
                self._pick(
                    payload,
                    "valve_open",
                    "valve",
                )
            ),
            active_cooling=self._bool(
                self._pick(
                    payload,
                    "active_cooling",
                    "cooling_active",
                )
            ),
            source=str(
                payload.get(
                    "source",
                    "unknown",
                )
            ),
            metadata=metadata,
        )

    def load_observations(
        self,
    ) -> tuple[
        list[NormalizedObservation],
        int,
        int,
    ]:
        if not self.observations_path.exists():
            return [], 0, 0

        observations: list[
            NormalizedObservation
        ] = []

        source_count = 0
        rejected_count = 0

        with self.observations_path.open(
            "r",
            encoding="utf-8",
        ) as handle:
            for raw_line in handle:
                line = raw_line.strip()

                if not line:
                    continue

                source_count += 1

                try:
                    payload = json.loads(line)
                except json.JSONDecodeError:
                    rejected_count += 1
                    continue

                if not isinstance(payload, dict):
                    rejected_count += 1
                    continue

                normalized = self._normalize(payload)

                if normalized is None:
                    rejected_count += 1
                    continue

                observations.append(normalized)

        observations.sort(
            key=lambda observation: observation.timestamp
        )

        return (
            observations,
            source_count,
            rejected_count,
        )

    @staticmethod
    def _confidence(
        sample_count: int,
        target_samples: int,
        coverage_hours: float,
        target_hours: float,
    ) -> float:
        sample_score = min(
            sample_count / max(target_samples, 1),
            1.0,
        )

        coverage_score = min(
            coverage_hours / max(target_hours, 1.0),
            1.0,
        )

        confidence = (
            sample_score * 0.70
            + coverage_score * 0.30
        ) * 100.0

        return round(confidence, 1)

    @staticmethod
    def _metric(
        values: Iterable[float],
        unit: str,
        coverage_hours: float,
        target_samples: int,
        target_hours: float,
    ) -> LearnedMetric:
        clean_values = [
            float(value)
            for value in values
            if math.isfinite(float(value))
        ]

        if not clean_values:
            return LearnedMetric(
                unit=unit,
            )

        sample_count = len(clean_values)

        return LearnedMetric(
            value=round(
                statistics.median(clean_values),
                4,
            ),
            unit=unit,
            sample_count=sample_count,
            confidence_percent=(
                ThermalLearningEngine._confidence(
                    sample_count=sample_count,
                    target_samples=target_samples,
                    coverage_hours=coverage_hours,
                    target_hours=target_hours,
                )
            ),
            minimum=round(
                min(clean_values),
                4,
            ),
            maximum=round(
                max(clean_values),
                4,
            ),
        )

    @staticmethod
    def _usable_transition(
        previous: NormalizedObservation,
        current: NormalizedObservation,
    ) -> tuple[bool, float]:
        duration_seconds = (
            current.timestamp
            - previous.timestamp
        ).total_seconds()

        if duration_seconds <= 0:
            return False, 0.0

        duration_hours = (
            duration_seconds / 3600.0
        )

        if duration_hours < (1.0 / 60.0):
            return False, duration_hours

        if duration_hours > 6.0:
            return False, duration_hours

        return True, duration_hours

    def train(
        self,
    ) -> ThermalLearningModel:
        (
            observations,
            source_count,
            rejected_count,
        ) = self.load_observations()

        model = ThermalLearningModel(
            source_observations=source_count,
            valid_observations=len(observations),
            rejected_observations=rejected_count,
        )

        if observations:
            model.observation_start = (
                observations[0]
                .timestamp
                .isoformat()
            )

            model.observation_end = (
                observations[-1]
                .timestamp
                .isoformat()
            )

            duration = (
                observations[-1].timestamp
                - observations[0].timestamp
            ).total_seconds() / 3600.0

            model.observation_duration_hours = round(
                max(duration, 0.0),
                3,
            )

        cooling_rates: list[float] = []
        warming_rates: list[float] = []
        hydraulic_deltas: list[float] = []
        surface_supply_deltas: list[float] = []
        hydraulic_powers: list[float] = []
        source_powers: list[float] = []

        active_transitions = 0
        passive_transitions = 0
        usable_transitions = 0

        for previous, current in zip(
            observations,
            observations[1:],
        ):
            usable, duration_hours = (
                self._usable_transition(
                    previous,
                    current,
                )
            )

            if not usable:
                continue

            usable_transitions += 1

            indoor_previous = (
                previous.indoor_temperature_c
            )
            indoor_current = (
                current.indoor_temperature_c
            )

            cooling_active = (
                previous.active_cooling
                and current.active_cooling
                and previous.pump_running
                and current.pump_running
                and previous.valve_open
                and current.valve_open
            )

            if (
                indoor_previous is not None
                and indoor_current is not None
            ):
                indoor_rate = (
                    indoor_current
                    - indoor_previous
                ) / duration_hours

                if cooling_active:
                    active_transitions += 1

                    if -5.0 <= indoor_rate <= 1.0:
                        cooling_rates.append(
                            indoor_rate
                        )
                else:
                    passive_transitions += 1

                    if -1.0 <= indoor_rate <= 5.0:
                        warming_rates.append(
                            indoor_rate
                        )

            supply = (
                current.floor_supply_temperature_c
            )
            returned = (
                current.floor_return_temperature_c
            )
            surface = (
                current.floor_surface_temperature_c
            )
            flow = current.flow_rate_l_min

            if (
                cooling_active
                and supply is not None
                and returned is not None
            ):
                delta = returned - supply

                if 0.0 <= delta <= 15.0:
                    hydraulic_deltas.append(delta)

                    if (
                        flow is not None
                        and 0.0 < flow <= 200.0
                    ):
                        hydraulic_powers.append(
                            WATER_POWER_FACTOR
                            * flow
                            * delta
                        )

            if (
                cooling_active
                and surface is not None
                and supply is not None
            ):
                surface_delta = surface - supply

                if -5.0 <= surface_delta <= 20.0:
                    surface_supply_deltas.append(
                        surface_delta
                    )

            source_in = (
                current.source_inlet_temperature_c
            )
            source_out = (
                current.source_outlet_temperature_c
            )

            if (
                cooling_active
                and flow is not None
                and source_in is not None
                and source_out is not None
                and 0.0 < flow <= 200.0
            ):
                source_delta = abs(
                    source_out - source_in
                )

                if 0.0 <= source_delta <= 20.0:
                    source_powers.append(
                        WATER_POWER_FACTOR
                        * flow
                        * source_delta
                    )

        coverage_hours = (
            model.observation_duration_hours
        )

        model.usable_transitions = (
            usable_transitions
        )

        model.active_cooling_transitions = (
            active_transitions
        )

        model.passive_transitions = (
            passive_transitions
        )

        model.building_cooling_rate = (
            self._metric(
                cooling_rates,
                unit="°C/h",
                coverage_hours=coverage_hours,
                target_samples=48,
                target_hours=72.0,
            )
        )

        model.building_passive_warming_rate = (
            self._metric(
                warming_rates,
                unit="°C/h",
                coverage_hours=coverage_hours,
                target_samples=48,
                target_hours=72.0,
            )
        )

        model.floor_supply_return_delta = (
            self._metric(
                hydraulic_deltas,
                unit="°C",
                coverage_hours=coverage_hours,
                target_samples=36,
                target_hours=48.0,
            )
        )

        model.floor_surface_supply_delta = (
            self._metric(
                surface_supply_deltas,
                unit="°C",
                coverage_hours=coverage_hours,
                target_samples=36,
                target_hours=48.0,
            )
        )

        model.hydraulic_power = self._metric(
            hydraulic_powers,
            unit="kW",
            coverage_hours=coverage_hours,
            target_samples=36,
            target_hours=48.0,
        )

        model.source_exchange_power = (
            self._metric(
                source_powers,
                unit="kW",
                coverage_hours=coverage_hours,
                target_samples=36,
                target_hours=48.0,
            )
        )

        metric_confidences = [
            metric.confidence_percent
            for metric in (
                model.building_cooling_rate,
                model.building_passive_warming_rate,
                model.floor_supply_return_delta,
                model.floor_surface_supply_delta,
                model.hydraulic_power,
                model.source_exchange_power,
            )
            if metric.sample_count > 0
        ]

        if metric_confidences:
            model.global_confidence_percent = round(
                statistics.mean(
                    metric_confidences
                ),
                1,
            )
        else:
            model.global_confidence_percent = 0.0

        if (
            model.valid_observations < 12
            or model.usable_transitions < 6
        ):
            model.status = "COLLECTING"
            model.learning_state = "COLLECTING"

        elif model.global_confidence_percent < 35.0:
            model.status = "LEARNING"
            model.learning_state = "EARLY_LEARNING"

        elif model.global_confidence_percent < 70.0:
            model.status = "LEARNING"
            model.learning_state = "CALIBRATING"

        else:
            model.status = "READY"
            model.learning_state = "LEARNED"

        recommendations: list[str] = []

        if model.valid_observations < 12:
            recommendations.append(
                "Collecter au moins 12 observations horodatées."
            )

        if coverage_hours < 24.0:
            recommendations.append(
                "Poursuivre la collecte sur au moins 24 heures."
            )

        if (
            model.building_cooling_rate.sample_count
            < 6
        ):
            recommendations.append(
                "Collecter plusieurs périodes de refroidissement actif."
            )

        if (
            model.building_passive_warming_rate.sample_count
            < 6
        ):
            recommendations.append(
                "Collecter des périodes sans refroidissement actif."
            )

        if (
            model.hydraulic_power.sample_count
            < 6
        ):
            recommendations.append(
                "Connecter les températures départ/retour et le débit hydraulique."
            )

        if not recommendations:
            recommendations.append(
                "Le modèle dispose d’un échantillon exploitable ; poursuivre l’apprentissage continu."
            )

        model.recommendations = recommendations

        self._atomic_write(
            model.to_dict()
        )

        return model

    def _atomic_write(
        self,
        payload: dict[str, Any],
    ) -> None:
        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        descriptor, temporary_name = (
            tempfile.mkstemp(
                dir=self.data_directory,
                prefix=".thermal-learning.",
                suffix=".tmp",
                text=True,
            )
        )

        temporary_path = Path(
            temporary_name
        )

        try:
            with os.fdopen(
                descriptor,
                "w",
                encoding="utf-8",
            ) as handle:
                json.dump(
                    payload,
                    handle,
                    ensure_ascii=False,
                    indent=2,
                    sort_keys=True,
                )

                handle.write("\n")
                handle.flush()
                os.fsync(handle.fileno())

            os.replace(
                temporary_path,
                self.model_path,
            )

        finally:
            if temporary_path.exists():
                temporary_path.unlink(
                    missing_ok=True
                )

    def read_model(
        self,
    ) -> dict[str, Any]:
        if not self.model_path.exists():
            return self.train().to_dict()

        try:
            payload = json.loads(
                self.model_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            json.JSONDecodeError,
            OSError,
        ):
            return self.train().to_dict()

        if not isinstance(payload, dict):
            return self.train().to_dict()

        return payload

    def status(
        self,
    ) -> dict[str, Any]:
        model = self.read_model()

        return {
            "version": self.VERSION,
            "status": model.get(
                "status",
                "COLLECTING",
            ),
            "learning_state": model.get(
                "learning_state",
                "COLLECTING",
            ),
            "global_confidence_percent": (
                model.get(
                    "global_confidence_percent",
                    0.0,
                )
            ),
            "source_observations": model.get(
                "source_observations",
                0,
            ),
            "valid_observations": model.get(
                "valid_observations",
                0,
            ),
            "usable_transitions": model.get(
                "usable_transitions",
                0,
            ),
            "model_path": str(
                self.model_path
            ),
            "model_exists": (
                self.model_path.exists()
            ),
            "data_directory_writable": (
                os.access(
                    self.data_directory,
                    os.W_OK,
                )
            ),
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
        }
