#!/usr/bin/env python3
from __future__ import annotations

import argparse
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def as_float(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def load_json(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise TypeError(f"{path} must contain a JSON object")

    return payload


def clamp(value: float, minimum: float, maximum: float) -> float:
    return max(minimum, min(maximum, value))


def calibrate(
    model: dict[str, Any],
    validation: dict[str, Any],
    *,
    learning_rate: float,
) -> dict[str, Any]:
    current_drift = as_float(
        model.get("indoor_drift_c_per_hour")
    ) or 0.0

    current_coupling = as_float(
        model.get("outdoor_coupling")
    ) or 0.0

    overall = validation.get("overall", {})
    bias = as_float(overall.get("bias_c"))
    mae = as_float(overall.get("mae_c"))
    matches = int(overall.get("matched_samples") or 0)

    notes: list[str] = []

    if bias is None or matches < 3:
        return {
            "schema": "geocooling.rc20c.thermal-twin-calibration.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "status": "INSUFFICIENT",
            "reason": "At least 3 matched validation samples are required.",
            "original_model": model,
            "calibrated_model": model,
            "adjustments": {
                "drift_delta_c_per_hour": 0.0,
                "coupling_delta": 0.0,
            },
            "safety": {
                "read_only": True,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }

    drift_delta = -bias * learning_rate
    calibrated_drift = current_drift + drift_delta

    coupling_delta = 0.0

    # Conservative coupling adjustment:
    # only tune it when the model has a measurable error and enough matches.
    if mae is not None and mae > 0.25 and matches >= 5:
        direction = -1.0 if bias > 0 else 1.0
        coupling_delta = direction * min(
            0.01,
            abs(bias) * learning_rate * 0.02,
        )

    calibrated_coupling = clamp(
        current_coupling + coupling_delta,
        -1.0,
        1.0,
    )

    if abs(drift_delta) > 0.5:
        notes.append(
            "Large drift correction was limited by the configured learning rate."
        )

    calibrated_model = dict(model)
    calibrated_model["generated_at"] = (
        datetime.now(timezone.utc).isoformat()
    )
    calibrated_model["source_model_generated_at"] = model.get(
        "generated_at"
    )
    calibrated_model["indoor_drift_c_per_hour"] = round(
        calibrated_drift,
        6,
    )
    calibrated_model["outdoor_coupling"] = round(
        calibrated_coupling,
        6,
    )
    calibrated_model["calibration"] = {
        "source_validation_generated_at": validation.get(
            "generated_at"
        ),
        "learning_rate": learning_rate,
        "matches": matches,
        "mae_c": mae,
        "bias_c": bias,
    }

    return {
        "schema": "geocooling.rc20c.thermal-twin-calibration.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "status": "CALIBRATED",
        "original_model": model,
        "calibrated_model": calibrated_model,
        "adjustments": {
            "drift_delta_c_per_hour": round(drift_delta, 6),
            "coupling_delta": round(coupling_delta, 6),
        },
        "notes": notes,
        "safety": {
            "read_only": True,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }


def resolve_session(
    data_root: Path,
    requested: str | None,
) -> Path:
    if requested:
        session = Path(requested)

        if not session.is_absolute():
            session = data_root / session

        return session

    sessions = sorted(
        path
        for path in data_root.glob("session-*")
        if path.is_dir()
    )

    if not sessions:
        raise FileNotFoundError(
            "No decision journal session found"
        )

    return sessions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="/opt/stacks/smart-building-controller/decision-journal",
    )
    parser.add_argument("--session")
    parser.add_argument(
        "--learning-rate",
        type=float,
        default=0.25,
    )
    args = parser.parse_args()

    if not 0.0 < args.learning_rate <= 1.0:
        raise SystemExit(
            "--learning-rate must be > 0 and <= 1"
        )

    data_root = Path(args.data_root)
    session = resolve_session(
        data_root,
        args.session,
    )

    twin_dir = session / "thermal-twin"
    model_file = twin_dir / "model.json"
    validation_file = (
        twin_dir
        / "validation"
        / "validation.json"
    )

    if not model_file.exists():
        raise FileNotFoundError(
            f"{model_file} — run BUILD_THERMAL_TWIN.sh first"
        )

    if not validation_file.exists():
        raise FileNotFoundError(
            f"{validation_file} — run VALIDATE_THERMAL_TWIN.sh first"
        )

    model = load_json(model_file)
    validation = load_json(validation_file)

    result = calibrate(
        model,
        validation,
        learning_rate=args.learning_rate,
    )

    output = twin_dir / "calibration"
    output.mkdir(parents=True, exist_ok=True)

    report_file = output / "calibration.json"
    model_output = output / "calibrated-model.json"

    report_file.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    model_output.write_text(
        json.dumps(
            result["calibrated_model"],
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print("============================================================")
    print(" RC2.0C — CALIBRATION TERMINÉE")
    print("============================================================")
    print("Session :", session)
    print("Statut  :", result["status"])
    print("Rapport :", report_file)
    print("Modèle  :", model_output)
    print()
    print(json.dumps(result["adjustments"], indent=2))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
