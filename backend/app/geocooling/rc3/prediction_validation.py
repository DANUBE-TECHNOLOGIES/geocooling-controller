"""
RC3.7 — prediction validation against later measured temperatures.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from math import isfinite, sqrt
from pathlib import Path
from statistics import fmean
from typing import Any, Iterable, Mapping
import json


@dataclass(frozen=True, slots=True)
class PredictionMatch:
    prediction_captured_at: str
    target_at: str
    actual_at: str
    scenario: str
    horizon_minutes: int
    predicted_indoor_temperature_c: float
    actual_indoor_temperature_c: float
    error_c: float
    absolute_error_c: float


def _number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    return result if isfinite(result) else None


def _timestamp(value: Any) -> datetime | None:
    if not isinstance(value, str):
        return None

    try:
        return datetime.fromisoformat(
            value.replace("Z", "+00:00")
        )
    except ValueError:
        return None


def _nested(payload: Mapping[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, Mapping):
            return None
        current = current.get(key)

    return current


def _load_jsonl(path: Path) -> Iterable[dict[str, Any]]:
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


class PredictionValidationEngine:
    def __init__(
        self,
        *,
        tolerance_minutes: int = 12,
    ) -> None:
        self.tolerance = timedelta(
            minutes=max(1, tolerance_minutes)
        )

    def validate(
        self,
        snapshots: list[dict[str, Any]],
    ) -> dict[str, Any]:
        measurements = self._measurement_index(snapshots)
        matches: list[PredictionMatch] = []

        for snapshot in snapshots:
            captured_at = _timestamp(
                snapshot.get("captured_at")
            )

            if captured_at is None:
                continue

            trajectories = _nested(
                snapshot,
                "prediction",
                "trajectories",
            )

            if not isinstance(trajectories, list):
                continue

            for trajectory in trajectories:
                if not isinstance(trajectory, Mapping):
                    continue

                scenario = str(
                    trajectory.get("scenario")
                    or "UNKNOWN"
                )
                points = trajectory.get("points")

                if not isinstance(points, list):
                    continue

                for point in points:
                    if not isinstance(point, Mapping):
                        continue

                    horizon = point.get("horizon_minutes")
                    predicted = _number(
                        point.get(
                            "predicted_indoor_temperature_c"
                        )
                    )

                    if (
                        not isinstance(horizon, int)
                        or predicted is None
                    ):
                        continue

                    target_at = captured_at + timedelta(
                        minutes=horizon
                    )
                    actual = self._nearest_measurement(
                        measurements,
                        target_at,
                    )

                    if actual is None:
                        continue

                    actual_at, actual_c = actual
                    error = predicted - actual_c

                    matches.append(
                        PredictionMatch(
                            prediction_captured_at=(
                                captured_at.isoformat()
                            ),
                            target_at=target_at.isoformat(),
                            actual_at=actual_at.isoformat(),
                            scenario=scenario,
                            horizon_minutes=horizon,
                            predicted_indoor_temperature_c=round(
                                predicted,
                                4,
                            ),
                            actual_indoor_temperature_c=round(
                                actual_c,
                                4,
                            ),
                            error_c=round(error, 4),
                            absolute_error_c=round(
                                abs(error),
                                4,
                            ),
                        )
                    )

        return self._report(matches)

    def _measurement_index(
        self,
        snapshots: list[dict[str, Any]],
    ) -> list[tuple[datetime, float]]:
        result = []

        for snapshot in snapshots:
            captured_at = _timestamp(
                snapshot.get("captured_at")
            )
            indoor = _number(
                _nested(
                    snapshot,
                    "context",
                    "measurements",
                    "indoor_temperature_c",
                )
            )

            if captured_at is not None and indoor is not None:
                result.append((captured_at, indoor))

        result.sort(key=lambda item: item[0])
        return result

    def _nearest_measurement(
        self,
        measurements: list[tuple[datetime, float]],
        target: datetime,
    ) -> tuple[datetime, float] | None:
        best = None
        best_delta = None

        for timestamp, temperature in measurements:
            delta = abs(timestamp - target)

            if delta > self.tolerance:
                continue

            if best_delta is None or delta < best_delta:
                best = (timestamp, temperature)
                best_delta = delta

        return best

    def _report(
        self,
        matches: list[PredictionMatch],
    ) -> dict[str, Any]:
        errors = [item.error_c for item in matches]

        if errors:
            mae = fmean(abs(error) for error in errors)
            rmse = sqrt(
                fmean(error * error for error in errors)
            )
            bias = fmean(errors)
        else:
            mae = None
            rmse = None
            bias = None

        by_horizon = {}

        for horizon in sorted(
            {item.horizon_minutes for item in matches}
        ):
            subset = [
                item
                for item in matches
                if item.horizon_minutes == horizon
                and item.scenario == "BASELINE"
            ]

            if not subset:
                continue

            subset_errors = [
                item.error_c
                for item in subset
            ]

            by_horizon[str(horizon)] = {
                "sample_count": len(subset),
                "mae_c": round(
                    fmean(abs(error) for error in subset_errors),
                    4,
                ),
                "rmse_c": round(
                    sqrt(
                        fmean(
                            error * error
                            for error in subset_errors
                        )
                    ),
                    4,
                ),
                "bias_c": round(
                    fmean(subset_errors),
                    4,
                ),
            }

        return {
            "schema": "geocooling.rc37.prediction-validation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "match_count": len(matches),
            "metrics": {
                "mae_c": round(mae, 4) if mae is not None else None,
                "rmse_c": round(rmse, 4) if rmse is not None else None,
                "bias_c": round(bias, 4) if bias is not None else None,
            },
            "by_horizon": by_horizon,
            "matches": [
                asdict(item)
                for item in matches
            ],
            "readiness": {
                "minimum_matches": 24,
                "enough_data": len(matches) >= 24,
            },
            "safety": {
                "analysis_only": True,
                "controller_authorized": False,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }


def load_latest_session(
    root: Path,
) -> list[dict[str, Any]]:
    sessions = sorted(
        path
        for path in root.glob("session-*")
        if path.is_dir()
    )

    if not sessions:
        return []

    source = sessions[-1] / "prediction-snapshots.jsonl"

    if not source.exists():
        return []

    return list(_load_jsonl(source))
