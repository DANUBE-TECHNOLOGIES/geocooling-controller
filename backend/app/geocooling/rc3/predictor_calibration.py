"""
RC3.6 — passive auto-calibration for the RC3.5 Weather/Inertia predictor.

The service estimates safer parameter updates from historical prediction errors.
It never writes parameters into the active predictor automatically.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from math import isfinite
from pathlib import Path
from statistics import fmean, median
from typing import Any, Iterable, Mapping, Sequence
import json


@dataclass(frozen=True, slots=True)
class CalibrationSample:
    horizon_minutes: int
    predicted_c: float
    actual_c: float
    error_c: float


@dataclass(frozen=True, slots=True)
class CalibrationProposal:
    fast_time_constant_hours: float
    slow_time_constant_hours: float
    mass_coupling: float
    solar_gain_c_per_hour_at_full_sun: float
    soft_cooling_c_per_hour: float
    full_cooling_c_per_hour: float
    model_confidence: float

    def as_dict(self) -> dict[str, float]:
        return asdict(self)


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if isfinite(result) else None


def _parse_lines(path: Path) -> Iterable[dict[str, Any]]:
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            stripped = line.strip()

            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError:
                continue

            if isinstance(payload, dict):
                yield payload


def _nested(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, Mapping):
            return None

        current = current.get(key)

    return current


def _clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


class PredictorCalibrationEngine:
    def __init__(
        self,
        *,
        minimum_samples: int = 12,
        learning_rate: float = 0.18,
    ) -> None:
        self.minimum_samples = max(3, minimum_samples)
        self.learning_rate = _clamp(learning_rate, 0.01, 0.50)

    def calibrate(
        self,
        *,
        current_model: Mapping[str, Any],
        samples: Sequence[CalibrationSample],
    ) -> dict[str, Any]:
        errors = [
            sample.error_c
            for sample in samples
            if isfinite(sample.error_c)
        ]

        if len(errors) < self.minimum_samples:
            return {
                "schema": "geocooling.rc36.calibration-report.v1",
                "generated_at": datetime.now(timezone.utc).isoformat(),
                "status": "INSUFFICIENT_DATA",
                "sample_count": len(errors),
                "minimum_samples": self.minimum_samples,
                "current_model": dict(current_model),
                "proposal": dict(current_model),
                "metrics": {},
                "activation": {
                    "automatic": False,
                    "requires_review": True,
                },
            }

        mae = fmean(abs(error) for error in errors)
        bias = fmean(errors)
        median_error = median(errors)

        short_errors = [
            sample.error_c
            for sample in samples
            if sample.horizon_minutes <= 120
        ]
        long_errors = [
            sample.error_c
            for sample in samples
            if sample.horizon_minutes >= 720
        ]

        short_bias = fmean(short_errors) if short_errors else bias
        long_bias = fmean(long_errors) if long_errors else bias

        fast_tau = _number(
            current_model.get("fast_time_constant_hours")
        ) or 2.5
        slow_tau = _number(
            current_model.get("slow_time_constant_hours")
        ) or 18.0
        coupling = _number(
            current_model.get("mass_coupling")
        ) or 0.28
        solar_gain = _number(
            current_model.get(
                "solar_gain_c_per_hour_at_full_sun"
            )
        ) or 0.20
        soft_cooling = _number(
            current_model.get("soft_cooling_c_per_hour")
        ) or 0.28
        full_cooling = _number(
            current_model.get("full_cooling_c_per_hour")
        ) or 0.52
        confidence = _number(
            current_model.get("model_confidence")
        ) or 0.62

        # Positive error means the model predicts too warm.
        # Increase inertia when long-horizon prediction changes too quickly.
        fast_tau *= 1.0 + self.learning_rate * _clamp(short_bias, -1.0, 1.0) * 0.20
        slow_tau *= 1.0 + self.learning_rate * _clamp(long_bias, -1.0, 1.0) * 0.30

        # Conservative coupling adjustment.
        coupling -= self.learning_rate * _clamp(bias, -1.0, 1.0) * 0.025

        # Solar gain is tuned slowly from systematic warm/cold bias.
        solar_gain -= self.learning_rate * _clamp(bias, -1.0, 1.0) * 0.015

        confidence_target = _clamp(
            1.0 - mae / 2.0,
            0.20,
            0.95,
        )
        confidence = (
            confidence * (1.0 - self.learning_rate)
            + confidence_target * self.learning_rate
        )

        proposal = CalibrationProposal(
            fast_time_constant_hours=round(
                _clamp(fast_tau, 0.8, 10.0),
                4,
            ),
            slow_time_constant_hours=round(
                _clamp(slow_tau, 6.0, 72.0),
                4,
            ),
            mass_coupling=round(
                _clamp(coupling, 0.05, 0.70),
                4,
            ),
            solar_gain_c_per_hour_at_full_sun=round(
                _clamp(solar_gain, 0.0, 0.80),
                4,
            ),
            soft_cooling_c_per_hour=round(
                _clamp(soft_cooling, 0.05, 1.50),
                4,
            ),
            full_cooling_c_per_hour=round(
                _clamp(full_cooling, 0.10, 2.50),
                4,
            ),
            model_confidence=round(
                _clamp(confidence, 0.20, 0.95),
                4,
            ),
        )

        return {
            "schema": "geocooling.rc36.calibration-report.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "PROPOSAL_READY",
            "sample_count": len(errors),
            "minimum_samples": self.minimum_samples,
            "metrics": {
                "mae_c": round(mae, 4),
                "bias_c": round(bias, 4),
                "median_error_c": round(median_error, 4),
                "short_horizon_bias_c": round(short_bias, 4),
                "long_horizon_bias_c": round(long_bias, 4),
            },
            "current_model": dict(current_model),
            "proposal": proposal.as_dict(),
            "activation": {
                "automatic": False,
                "requires_review": True,
            },
            "safety": {
                "controller_authorized": False,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }


def collect_samples_from_journals(
    roots: Sequence[Path],
) -> tuple[CalibrationSample, ...]:
    samples: list[CalibrationSample] = []

    for root in roots:
        if not root.exists():
            continue

        for path in root.rglob("*.jsonl"):
            for payload in _parse_lines(path):
                # Accept explicit validation rows when available.
                horizon = _number(payload.get("horizon_minutes"))
                predicted = _number(
                    payload.get(
                        "predicted_indoor_temperature_c"
                    )
                )
                actual = _number(
                    payload.get(
                        "actual_indoor_temperature_c"
                    )
                )

                if (
                    horizon is not None
                    and predicted is not None
                    and actual is not None
                ):
                    samples.append(
                        CalibrationSample(
                            horizon_minutes=int(horizon),
                            predicted_c=predicted,
                            actual_c=actual,
                            error_c=predicted - actual,
                        )
                    )
                    continue

                # Also accept nested RC3.5 validation-compatible rows.
                matches = payload.get("matches")

                if isinstance(matches, list):
                    for item in matches:
                        if not isinstance(item, Mapping):
                            continue

                        horizon = _number(
                            item.get("horizon_minutes")
                        )
                        predicted = _number(
                            item.get(
                                "predicted_indoor_temperature_c"
                            )
                        )
                        actual = _number(
                            item.get(
                                "actual_indoor_temperature_c"
                            )
                        )

                        if (
                            horizon is None
                            or predicted is None
                            or actual is None
                        ):
                            continue

                        samples.append(
                            CalibrationSample(
                                horizon_minutes=int(horizon),
                                predicted_c=predicted,
                                actual_c=actual,
                                error_c=predicted - actual,
                            )
                        )

    return tuple(samples)
