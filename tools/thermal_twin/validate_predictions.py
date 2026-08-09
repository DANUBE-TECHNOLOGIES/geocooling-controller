#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from dataclasses import dataclass, asdict
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class ValidationMetric:
    horizon_minutes: int
    matched_samples: int
    mae_c: float | None
    rmse_c: float | None
    bias_c: float | None
    max_abs_error_c: float | None
    quality: str

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
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def load_contexts(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []

    with path.open("r", encoding="utf-8") as stream:
        for line_number, line in enumerate(stream, start=1):
            stripped = line.strip()

            if not stripped:
                continue

            try:
                payload = json.loads(stripped)
            except json.JSONDecodeError as exc:
                raise ValueError(
                    f"Invalid JSON at line {line_number}: {exc}"
                ) from exc

            if isinstance(payload, dict):
                timestamp = parse_timestamp(payload.get("timestamp"))
                indoor = as_float(
                    nested(
                        payload,
                        "measurements",
                        "indoor_temperature_c",
                    )
                )

                if timestamp is not None and indoor is not None:
                    rows.append(
                        {
                            "timestamp": timestamp,
                            "indoor": indoor,
                            "payload": payload,
                        }
                    )

    rows.sort(key=lambda item: item["timestamp"])
    return rows


def load_prediction(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))

    if not isinstance(payload, dict):
        raise TypeError("Prediction payload must be a JSON object")

    return payload


def nearest_actual(
    contexts: list[dict[str, Any]],
    target: datetime,
    tolerance_seconds: float,
) -> dict[str, Any] | None:
    best = None
    best_delta = None

    for item in contexts:
        delta = abs(
            (item["timestamp"] - target).total_seconds()
        )

        if delta > tolerance_seconds:
            continue

        if best_delta is None or delta < best_delta:
            best = item
            best_delta = delta

    return best


def metric(
    horizon_minutes: int,
    errors: list[float],
) -> ValidationMetric:
    if not errors:
        return ValidationMetric(
            horizon_minutes=horizon_minutes,
            matched_samples=0,
            mae_c=None,
            rmse_c=None,
            bias_c=None,
            max_abs_error_c=None,
            quality="INSUFFICIENT",
        )

    mae = statistics.fmean(abs(error) for error in errors)
    rmse = math.sqrt(
        statistics.fmean(error * error for error in errors)
    )
    bias = statistics.fmean(errors)
    max_abs = max(abs(error) for error in errors)

    if len(errors) < 3:
        quality = "INSUFFICIENT"
    elif mae <= 0.25:
        quality = "EXCELLENT"
    elif mae <= 0.50:
        quality = "GOOD"
    elif mae <= 1.00:
        quality = "DEGRADED"
    else:
        quality = "POOR"

    return ValidationMetric(
        horizon_minutes=horizon_minutes,
        matched_samples=len(errors),
        mae_c=round(mae, 4),
        rmse_c=round(rmse, 4),
        bias_c=round(bias, 4),
        max_abs_error_c=round(max_abs, 4),
        quality=quality,
    )


def build_validation(
    contexts: list[dict[str, Any]],
    prediction_payload: dict[str, Any],
    tolerance_seconds: float,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    generated_at = parse_timestamp(
        prediction_payload.get("generated_at")
    )

    if generated_at is None:
        generated_at = contexts[-1]["timestamp"]

    predictions = prediction_payload.get("predictions", [])

    if not isinstance(predictions, list):
        raise TypeError("predictions must be a list")

    matches: list[dict[str, Any]] = []
    errors_by_horizon: dict[int, list[float]] = {}

    for item in predictions:
        if not isinstance(item, dict):
            continue

        horizon = item.get("horizon_minutes")
        predicted = as_float(
            item.get("predicted_indoor_temperature_c")
        )

        if not isinstance(horizon, int) or predicted is None:
            continue

        target = generated_at + timedelta(minutes=horizon)
        actual = nearest_actual(
            contexts,
            target,
            tolerance_seconds,
        )

        if actual is None:
            continue

        error = predicted - actual["indoor"]

        matches.append(
            {
                "horizon_minutes": horizon,
                "prediction_generated_at": generated_at.isoformat(),
                "target_timestamp": target.isoformat(),
                "actual_timestamp": actual["timestamp"].isoformat(),
                "predicted_indoor_temperature_c": round(predicted, 4),
                "actual_indoor_temperature_c": round(
                    actual["indoor"],
                    4,
                ),
                "error_c": round(error, 4),
                "absolute_error_c": round(abs(error), 4),
            }
        )

        errors_by_horizon.setdefault(horizon, []).append(error)

    metrics = [
        metric(horizon, errors)
        for horizon, errors in sorted(errors_by_horizon.items())
    ]

    overall_errors = [
        item["error_c"]
        for item in matches
    ]

    overall = metric(
        horizon_minutes=0,
        errors=overall_errors,
    )

    report = {
        "schema": "geocooling.rc20b.thermal-twin-validation.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "prediction_generated_at": generated_at.isoformat(),
        "tolerance_seconds": tolerance_seconds,
        "matches": len(matches),
        "overall": overall.as_dict(),
        "by_horizon": [
            item.as_dict()
            for item in metrics
        ],
        "safety": {
            "read_only": True,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }

    return report, matches


def write_csv(
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    if not rows:
        path.write_text("", encoding="utf-8")
        return

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=list(rows[0]),
        )
        writer.writeheader()
        writer.writerows(rows)


def write_markdown(
    report: dict[str, Any],
    path: Path,
) -> None:
    overall = report["overall"]

    lines = [
        "# RC2.0B — Validation du jumeau thermique",
        "",
        f"**Généré le :** {report['generated_at']}",
        f"**Prédiction générée le :** {report['prediction_generated_at']}",
        f"**Correspondances :** {report['matches']}",
        "",
        "## Résultat global",
        "",
        "| Indicateur | Valeur |",
        "|---|---:|",
        f"| MAE | {overall['mae_c']} °C |",
        f"| RMSE | {overall['rmse_c']} °C |",
        f"| Biais | {overall['bias_c']} °C |",
        f"| Erreur absolue maximale | {overall['max_abs_error_c']} °C |",
        f"| Qualité | {overall['quality']} |",
        "",
        "## Par horizon",
        "",
        "| Horizon | Échantillons | MAE | RMSE | Biais | Max | Qualité |",
        "|---:|---:|---:|---:|---:|---:|---|",
    ]

    for item in report["by_horizon"]:
        lines.append(
            "| "
            + " | ".join(
                [
                    f"{item['horizon_minutes']} min",
                    str(item["matched_samples"]),
                    str(item["mae_c"]),
                    str(item["rmse_c"]),
                    str(item["bias_c"]),
                    str(item["max_abs_error_c"]),
                    str(item["quality"]),
                ]
            )
            + " |"
        )

    lines.extend(
        [
            "",
            "## Interprétation",
            "",
            "- EXCELLENT : MAE ≤ 0,25 °C",
            "- GOOD : MAE ≤ 0,50 °C",
            "- DEGRADED : MAE ≤ 1,00 °C",
            "- POOR : MAE > 1,00 °C",
            "",
            "Le biais positif signifie que le modèle surestime la température.",
            "Le biais négatif signifie qu’il la sous-estime.",
            "",
            "## Garanties",
            "",
            "- analyse locale uniquement ;",
            "- aucune API appelée ;",
            "- aucune commande matérielle ;",
            "- aucune écriture MQTT ;",
            "- aucune écriture dans la base applicative.",
        ]
    )

    path.write_text(
        "\n".join(lines) + "\n",
        encoding="utf-8",
    )


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
        "--tolerance-seconds",
        type=float,
        default=90.0,
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    session = resolve_session(
        data_root,
        args.session,
    )

    contexts_file = session / "contexts.jsonl"
    prediction_file = session / "thermal-twin" / "prediction.json"

    if not contexts_file.exists():
        raise FileNotFoundError(contexts_file)

    if not prediction_file.exists():
        raise FileNotFoundError(
            f"{prediction_file} — run BUILD_THERMAL_TWIN.sh first"
        )

    contexts = load_contexts(contexts_file)
    prediction_payload = load_prediction(prediction_file)

    report, matches = build_validation(
        contexts,
        prediction_payload,
        args.tolerance_seconds,
    )

    output = session / "thermal-twin" / "validation"
    output.mkdir(parents=True, exist_ok=True)

    json_file = output / "validation.json"
    md_file = output / "VALIDATION.md"
    csv_file = output / "matches.csv"

    json_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_markdown(report, md_file)
    write_csv(matches, csv_file)

    print("============================================================")
    print(" RC2.0B — VALIDATION TERMINÉE")
    print("============================================================")
    print("Session :", session)
    print("Matches :", report["matches"])
    print("MAE     :", report["overall"]["mae_c"])
    print("RMSE    :", report["overall"]["rmse_c"])
    print("Qualité :", report["overall"]["quality"])
    print("Rapport :", md_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
