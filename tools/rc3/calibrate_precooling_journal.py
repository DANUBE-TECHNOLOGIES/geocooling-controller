#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from collections import defaultdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from statistics import mean
from typing import Any


def parse_dt(value: Any) -> datetime | None:
    if not value:
        return None
    try:
        dt = datetime.fromisoformat(str(value).replace("Z", "+00:00"))
    except (TypeError, ValueError):
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


def number(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None
    return result if math.isfinite(result) else None


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    with path.open("r", encoding="utf-8") as stream:
        for line in stream:
            line = line.strip()
            if not line:
                continue
            payload = json.loads(line)
            if isinstance(payload, dict):
                rows.append(payload)
    return rows


def current_indoor(row: dict[str, Any]) -> float | None:
    context = row.get("context")
    if not isinstance(context, dict):
        return None
    candidates = [
        context.get("indoor_temperature_c"),
        context.get("temperature_indoor_c"),
    ]
    thermal = context.get("thermal")
    if isinstance(thermal, dict):
        candidates.extend(
            [thermal.get("indoor_temperature_c"), thermal.get("temperature_c")]
        )
    for value in candidates:
        result = number(value)
        if result is not None:
            return result
    return None


def baseline_points(row: dict[str, Any]) -> list[dict[str, Any]]:
    prediction = row.get("prediction")
    if not isinstance(prediction, dict):
        return []
    trajectories = prediction.get("trajectories")
    if not isinstance(trajectories, list):
        return []
    for trajectory in trajectories:
        if not isinstance(trajectory, dict):
            continue
        if trajectory.get("scenario") != "BASELINE":
            continue
        points = trajectory.get("points")
        if isinstance(points, list):
            return [item for item in points if isinstance(item, dict)]
    return []


def captured_at(row: dict[str, Any]) -> datetime | None:
    return parse_dt(row.get("captured_at"))


def closest_observation(
    observations: list[tuple[datetime, float]],
    target: datetime,
    tolerance: timedelta,
) -> tuple[datetime, float] | None:
    best: tuple[datetime, float] | None = None
    best_delta: timedelta | None = None
    for item in observations:
        delta = abs(item[0] - target)
        if delta > tolerance:
            continue
        if best_delta is None or delta < best_delta:
            best = item
            best_delta = delta
    return best


def analyse(path: Path, tolerance_minutes: int) -> dict[str, Any]:
    rows = load_rows(path)
    observations: list[tuple[datetime, float]] = []
    for row in rows:
        ts = captured_at(row)
        temp = current_indoor(row)
        if ts is not None and temp is not None:
            observations.append((ts, temp))
    observations.sort(key=lambda item: item[0])

    by_horizon: dict[int, list[float]] = defaultdict(list)
    signed_by_horizon: dict[int, list[float]] = defaultdict(list)
    confidence_pairs: list[tuple[float, float]] = []
    matches = 0

    tolerance = timedelta(minutes=max(1, tolerance_minutes))

    for row in rows:
        base = captured_at(row)
        if base is None:
            continue
        for point in baseline_points(row):
            try:
                horizon = int(point.get("horizon_minutes"))
            except (TypeError, ValueError):
                continue
            predicted = number(point.get("predicted_indoor_temperature_c"))
            if predicted is None or horizon <= 0:
                continue
            actual_match = closest_observation(
                observations,
                base + timedelta(minutes=horizon),
                tolerance,
            )
            if actual_match is None:
                continue
            actual = actual_match[1]
            error = predicted - actual
            by_horizon[horizon].append(abs(error))
            signed_by_horizon[horizon].append(error)
            confidence = number(point.get("confidence"))
            if confidence is not None:
                confidence_pairs.append((confidence, abs(error)))
            matches += 1

    horizon_metrics: list[dict[str, Any]] = []
    all_abs: list[float] = []
    all_signed: list[float] = []
    for horizon in sorted(by_horizon):
        abs_errors = by_horizon[horizon]
        signed_errors = signed_by_horizon[horizon]
        all_abs.extend(abs_errors)
        all_signed.extend(signed_errors)
        horizon_metrics.append(
            {
                "horizon_minutes": horizon,
                "matches": len(abs_errors),
                "mae_c": round(mean(abs_errors), 3),
                "bias_c": round(mean(signed_errors), 3),
                "max_abs_error_c": round(max(abs_errors), 3),
            }
        )

    overall_mae = mean(all_abs) if all_abs else None
    overall_bias = mean(all_signed) if all_signed else None

    status = "INSUFFICIENT_DATA"
    if matches >= 12 and overall_mae is not None:
        if overall_mae <= 0.5:
            status = "WELL_CALIBRATED"
        elif overall_mae <= 1.0:
            status = "USABLE_WITH_CAUTION"
        else:
            status = "RECALIBRATION_RECOMMENDED"

    return {
        "schema": "geocooling.rc35.precooling-calibration-report.v1",
        "journal": str(path),
        "samples": len(rows),
        "matched_predictions": matches,
        "tolerance_minutes": tolerance_minutes,
        "status": status,
        "overall": {
            "mae_c": round(overall_mae, 3) if overall_mae is not None else None,
            "bias_c": round(overall_bias, 3) if overall_bias is not None else None,
        },
        "by_horizon": horizon_metrics,
        "safety": {
            "analysis_only": True,
            "auto_tuning": False,
            "controller_authorized": False,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("journal", type=Path)
    parser.add_argument("--tolerance-minutes", type=int, default=8)
    args = parser.parse_args()

    if not args.journal.is_file():
        raise SystemExit(f"Journal introuvable: {args.journal}")

    print(
        json.dumps(
            analyse(args.journal, args.tolerance_minutes),
            ensure_ascii=False,
            indent=2,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
