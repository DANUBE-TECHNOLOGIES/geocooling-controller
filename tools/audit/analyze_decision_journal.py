#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import math
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable


def load_jsonl(path: Path) -> list[dict[str, Any]]:
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
                rows.append(payload)

    return rows


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def number(value: Any) -> float | None:
    try:
        converted = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(converted):
        return None

    return converted


def boolean(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "yes", "1", "on"}:
            return True

        if normalized in {"false", "no", "0", "off"}:
            return False

    return None


def values(
    rows: Iterable[dict[str, Any]],
    *path: str,
) -> list[float]:
    result: list[float] = []

    for row in rows:
        value = number(nested(row, *path))

        if value is not None:
            result.append(value)

    return result


def metric(values_list: list[float]) -> dict[str, float | int | None]:
    if not values_list:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
        }

    return {
        "count": len(values_list),
        "min": round(min(values_list), 3),
        "max": round(max(values_list), 3),
        "mean": round(statistics.fmean(values_list), 3),
        "median": round(statistics.median(values_list), 3),
    }


def distribution(
    rows: Iterable[dict[str, Any]],
    *path: str,
) -> dict[str, int]:
    counter: Counter[str] = Counter()

    for row in rows:
        value = nested(row, *path)

        if value is None:
            value = "UNKNOWN"

        counter[str(value)] += 1

    return dict(sorted(counter.items()))


def availability_rate(
    rows: list[dict[str, Any]],
    source: str,
) -> float:
    if not rows:
        return 0.0

    available = 0

    for row in rows:
        value = boolean(
            nested(
                row,
                "availability",
                source,
            )
        )

        if value is True:
            available += 1

    return round(available / len(rows), 4)


def risk_distribution(
    rows: list[dict[str, Any]],
) -> dict[str, int]:
    counter: Counter[str] = Counter()

    for row in rows:
        risks = row.get("risks")

        if not isinstance(risks, list):
            continue

        for risk in risks:
            if isinstance(risk, dict):
                code = str(risk.get("code") or "UNKNOWN")
                counter[code] += 1

    return dict(counter.most_common())


def build_report(
    rows: list[dict[str, Any]],
    session: Path,
) -> dict[str, Any]:
    indoor = values(rows, "measurements", "indoor_temperature_c")
    outdoor = values(rows, "measurements", "outdoor_temperature_c")
    humidity = values(rows, "measurements", "indoor_humidity_pct")
    dew_point = values(rows, "measurements", "dew_point_c")
    margin = values(rows, "configuration", "condensation_margin_c")
    confidence = values(rows, "recommendation", "confidence")

    blocking_count = sum(
        1
        for row in rows
        if boolean(row.get("blocking")) is True
    )

    report = {
        "schema": "geocooling.rc17e.decision-analysis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": str(session),
        "sample_count": len(rows),
        "metrics": {
            "indoor_temperature_c": metric(indoor),
            "outdoor_temperature_c": metric(outdoor),
            "indoor_humidity_pct": metric(humidity),
            "dew_point_c": metric(dew_point),
            "condensation_margin_c": metric(margin),
            "confidence": metric(confidence),
        },
        "decision_distribution": distribution(
            rows,
            "recommendation",
            "action",
        ),
        "risk_level_distribution": distribution(
            rows,
            "highest_risk_level",
        ),
        "risk_code_distribution": risk_distribution(rows),
        "blocking": {
            "count": blocking_count,
            "rate": (
                round(blocking_count / len(rows), 4)
                if rows
                else 0.0
            ),
        },
        "availability": {
            source: availability_rate(rows, source)
            for source in (
                "weather",
                "historian",
                "learning",
                "prediction",
                "hardware",
            )
        },
        "quality": {
            source: distribution(rows, "quality", source)
            for source in (
                "sensors",
                "weather",
                "learning",
                "prediction",
            )
        },
        "safety": {
            "read_only_analysis": True,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }

    return report


def markdown_table(headers: list[str], rows: list[list[Any]]) -> str:
    if not rows:
        return "_Aucune donnée._"

    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]

    for row in rows:
        lines.append(
            "| "
            + " | ".join(
                str(value).replace("|", "\\|")
                for value in row
            )
            + " |"
        )

    return "\n".join(lines)


def write_markdown(
    report: dict[str, Any],
    path: Path,
) -> None:
    metrics = report["metrics"]

    metric_rows = []

    for name, item in metrics.items():
        metric_rows.append([
            name,
            item["count"],
            item["min"],
            item["max"],
            item["mean"],
            item["median"],
        ])

    decision_rows = [
        [name, count]
        for name, count in report["decision_distribution"].items()
    ]

    risk_rows = [
        [name, count]
        for name, count in report["risk_code_distribution"].items()
    ]

    availability_rows = [
        [name, f"{rate * 100:.1f}%"]
        for name, rate in report["availability"].items()
    ]

    markdown = f"""# RC1.7E — Analyse du journal de décision

**Session :** `{report["session"]}`  
**Échantillons :** {report["sample_count"]}  
**Généré le :** {report["generated_at"]}

## Synthèse

- Décisions bloquées : **{report["blocking"]["count"]}**
- Taux de blocage : **{report["blocking"]["rate"] * 100:.1f}%**
- Analyse strictement passive : **oui**

## Mesures

{markdown_table(
    ["Mesure", "N", "Min", "Max", "Moyenne", "Médiane"],
    metric_rows,
)}

## Répartition des décisions

{markdown_table(
    ["Décision", "Occurrences"],
    decision_rows,
)}

## Risques détectés

{markdown_table(
    ["Code", "Occurrences"],
    risk_rows,
)}

## Disponibilité des sources

{markdown_table(
    ["Source", "Disponibilité"],
    availability_rows,
)}

## Niveaux de risque

{markdown_table(
    ["Niveau", "Occurrences"],
    [
        [name, count]
        for name, count in report["risk_level_distribution"].items()
    ],
)}

## Qualité des données
"""

    for source, dist in report["quality"].items():
        markdown += f"\n### {source}\n\n"
        markdown += markdown_table(
            ["Qualité", "Occurrences"],
            [
                [name, count]
                for name, count in dist.items()
            ],
        )
        markdown += "\n"

    markdown += """
## Interprétation

Ce rapport décrit le comportement passif du Decision Context. Il ne prouve pas
encore la justesse thermique des recommandations : cette validation nécessitera
de comparer les prédictions aux températures réellement observées plusieurs
heures plus tard.

## Garanties

- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture dans la base applicative ;
- analyse locale des fichiers du journal uniquement.
"""

    path.write_text(markdown, encoding="utf-8")


def write_flat_csv(
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    columns = [
        "timestamp",
        "action",
        "confidence",
        "blocking",
        "risk_level",
        "indoor_temperature_c",
        "outdoor_temperature_c",
        "indoor_humidity_pct",
        "dew_point_c",
        "condensation_margin_c",
        "weather_available",
        "historian_available",
        "learning_available",
        "prediction_available",
        "hardware_available",
    ]

    with path.open("w", newline="", encoding="utf-8") as stream:
        writer = csv.DictWriter(stream, fieldnames=columns)
        writer.writeheader()

        for row in rows:
            writer.writerow({
                "timestamp": row.get("timestamp"),
                "action": nested(row, "recommendation", "action"),
                "confidence": nested(row, "recommendation", "confidence"),
                "blocking": row.get("blocking"),
                "risk_level": row.get("highest_risk_level"),
                "indoor_temperature_c": nested(
                    row,
                    "measurements",
                    "indoor_temperature_c",
                ),
                "outdoor_temperature_c": nested(
                    row,
                    "measurements",
                    "outdoor_temperature_c",
                ),
                "indoor_humidity_pct": nested(
                    row,
                    "measurements",
                    "indoor_humidity_pct",
                ),
                "dew_point_c": nested(
                    row,
                    "measurements",
                    "dew_point_c",
                ),
                "condensation_margin_c": nested(
                    row,
                    "configuration",
                    "condensation_margin_c",
                ),
                "weather_available": nested(
                    row,
                    "availability",
                    "weather",
                ),
                "historian_available": nested(
                    row,
                    "availability",
                    "historian",
                ),
                "learning_available": nested(
                    row,
                    "availability",
                    "learning",
                ),
                "prediction_available": nested(
                    row,
                    "availability",
                    "prediction",
                ),
                "hardware_available": nested(
                    row,
                    "availability",
                    "hardware",
                ),
            })


def resolve_session(
    data_root: Path,
    requested: str | None,
) -> Path:
    if requested:
        session = Path(requested)

        if not session.is_absolute():
            session = data_root / session

        return session

    active = data_root / ".active"

    if active.exists():
        candidate = Path(
            active.read_text(encoding="utf-8").strip()
        )

        if candidate.exists():
            return candidate

    sessions = sorted(
        path
        for path in data_root.glob("session-*")
        if path.is_dir()
    )

    if not sessions:
        raise FileNotFoundError("No decision journal session found")

    return sessions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--session")
    parser.add_argument(
        "--data-root",
        default="/opt/stacks/smart-building-controller/decision-journal",
    )
    args = parser.parse_args()

    data_root = Path(args.data_root)
    session = resolve_session(data_root, args.session)
    source = session / "contexts.jsonl"

    if not source.exists():
        raise FileNotFoundError(source)

    rows = load_jsonl(source)
    report = build_report(rows, session)

    output = session / "analysis"
    output.mkdir(parents=True, exist_ok=True)

    json_file = output / "analysis.json"
    md_file = output / "ANALYSIS.md"
    csv_file = output / "samples-flat.csv"

    json_file.write_text(
        json.dumps(report, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    write_markdown(report, md_file)
    write_flat_csv(rows, csv_file)

    print("============================================================")
    print(" RC1.7E — ANALYSE TERMINÉE")
    print("============================================================")
    print("Session     :", session)
    print("Échantillons:", len(rows))
    print("Rapport     :", md_file)
    print("JSON        :", json_file)
    print("CSV         :", csv_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
