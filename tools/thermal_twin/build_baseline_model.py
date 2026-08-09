#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ThermalTwinModel:
    schema: str
    generated_at: str
    sample_count: int
    interval_seconds_median: float | None
    indoor_drift_c_per_hour: float | None
    outdoor_coupling: float | None
    inertia_class: str
    prediction_horizons_minutes: list[int]
    quality: str
    notes: list[str]

    def as_dict(self) -> dict[str, Any]:
        return asdict(self)


def parse_timestamp(value: str | None) -> datetime | None:
    if not value:
        return None

    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


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


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None
        current = current.get(key)

    return current


def prepare_points(rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    points: list[dict[str, Any]] = []

    for row in rows:
        timestamp = parse_timestamp(row.get("timestamp"))
        indoor = as_float(nested(row, "measurements", "indoor_temperature_c"))
        outdoor = as_float(nested(row, "measurements", "outdoor_temperature_c"))

        if timestamp is None or indoor is None:
            continue

        points.append({
            "timestamp": timestamp,
            "indoor": indoor,
            "outdoor": outdoor,
        })

    points.sort(key=lambda item: item["timestamp"])
    return points


def estimate_model(points: list[dict[str, Any]]) -> ThermalTwinModel:
    notes: list[str] = []

    if len(points) < 3:
        return ThermalTwinModel(
            schema="geocooling.rc20a.thermal-twin-baseline.v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
            sample_count=len(points),
            interval_seconds_median=None,
            indoor_drift_c_per_hour=None,
            outdoor_coupling=None,
            inertia_class="UNKNOWN",
            prediction_horizons_minutes=[30, 60, 120, 240],
            quality="INSUFFICIENT",
            notes=["At least 3 valid samples are required."],
        )

    intervals = []
    drift_rates = []
    coupling_pairs = []

    for previous, current in zip(points, points[1:]):
        seconds = (
            current["timestamp"] - previous["timestamp"]
        ).total_seconds()

        if seconds <= 0:
            continue

        intervals.append(seconds)

        delta_indoor = current["indoor"] - previous["indoor"]
        hours = seconds / 3600.0
        drift_rates.append(delta_indoor / hours)

        if previous["outdoor"] is not None:
            delta_to_outdoor = previous["outdoor"] - previous["indoor"]
            coupling_pairs.append((delta_to_outdoor, delta_indoor / hours))

    interval_median = statistics.median(intervals) if intervals else None
    drift = statistics.median(drift_rates) if drift_rates else None

    coupling = None

    if len(coupling_pairs) >= 3:
        xs = [pair[0] for pair in coupling_pairs]
        ys = [pair[1] for pair in coupling_pairs]
        x_mean = statistics.fmean(xs)
        y_mean = statistics.fmean(ys)

        numerator = sum(
            (x - x_mean) * (y - y_mean)
            for x, y in coupling_pairs
        )
        denominator = sum(
            (x - x_mean) ** 2
            for x in xs
        )

        if denominator > 0:
            coupling = numerator / denominator

    if drift is None:
        inertia = "UNKNOWN"
    else:
        absolute_drift = abs(drift)

        if absolute_drift < 0.10:
            inertia = "VERY_HIGH"
        elif absolute_drift < 0.25:
            inertia = "HIGH"
        elif absolute_drift < 0.50:
            inertia = "MEDIUM"
        else:
            inertia = "LOW"

    if len(points) < 20:
        quality = "DEGRADED"
        notes.append("Model based on fewer than 20 samples.")
    else:
        quality = "GOOD"

    if coupling is None:
        notes.append("Outdoor coupling could not be estimated reliably.")

    return ThermalTwinModel(
        schema="geocooling.rc20a.thermal-twin-baseline.v1",
        generated_at=datetime.now(timezone.utc).isoformat(),
        sample_count=len(points),
        interval_seconds_median=(
            round(interval_median, 3)
            if interval_median is not None
            else None
        ),
        indoor_drift_c_per_hour=(
            round(drift, 6)
            if drift is not None
            else None
        ),
        outdoor_coupling=(
            round(coupling, 6)
            if coupling is not None
            else None
        ),
        inertia_class=inertia,
        prediction_horizons_minutes=[30, 60, 120, 240],
        quality=quality,
        notes=notes,
    )


def predict(
    model: ThermalTwinModel,
    *,
    indoor_temperature_c: float,
    outdoor_temperature_c: float | None,
) -> dict[str, Any]:
    baseline_drift = model.indoor_drift_c_per_hour or 0.0
    coupling = model.outdoor_coupling or 0.0

    predictions = []

    for horizon in model.prediction_horizons_minutes:
        hours = horizon / 60.0
        effective_drift = baseline_drift

        if outdoor_temperature_c is not None:
            effective_drift += (
                coupling
                * (outdoor_temperature_c - indoor_temperature_c)
            )

        predictions.append({
            "horizon_minutes": horizon,
            "predicted_indoor_temperature_c": round(
                indoor_temperature_c + effective_drift * hours,
                3,
            ),
        })

    return {
        "schema": "geocooling.rc20a.thermal-twin-prediction.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "model_quality": model.quality,
        "inertia_class": model.inertia_class,
        "predictions": predictions,
        "safety": {
            "read_only": True,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }


def latest_session(data_root: Path) -> Path:
    sessions = sorted(
        path
        for path in data_root.glob("session-*")
        if path.is_dir()
    )

    if not sessions:
        raise FileNotFoundError("No decision journal session found.")

    return sessions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="/opt/stacks/smart-building-controller/decision-journal",
    )
    parser.add_argument("--session")
    parser.add_argument("--indoor", type=float)
    parser.add_argument("--outdoor", type=float)
    args = parser.parse_args()

    data_root = Path(args.data_root)
    session = (
        Path(args.session)
        if args.session
        else latest_session(data_root)
    )

    if not session.is_absolute():
        session = data_root / session

    rows = load_rows(session / "contexts.jsonl")
    points = prepare_points(rows)
    model = estimate_model(points)

    output = session / "thermal-twin"
    output.mkdir(parents=True, exist_ok=True)

    model_file = output / "model.json"
    model_file.write_text(
        json.dumps(model.as_dict(), indent=2),
        encoding="utf-8",
    )

    indoor = args.indoor
    outdoor = args.outdoor

    if indoor is None and points:
        indoor = points[-1]["indoor"]

    if outdoor is None and points:
        outdoor = points[-1]["outdoor"]

    if indoor is not None:
        prediction = predict(
            model,
            indoor_temperature_c=indoor,
            outdoor_temperature_c=outdoor,
        )

        prediction_file = output / "prediction.json"
        prediction_file.write_text(
            json.dumps(prediction, indent=2),
            encoding="utf-8",
        )

        print(json.dumps(prediction, indent=2))

    print()
    print("Model:", model_file)
    print("Quality:", model.quality)
    print("Inertia:", model.inertia_class)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
