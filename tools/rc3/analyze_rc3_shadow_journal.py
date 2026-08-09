#!/usr/bin/env python3
from __future__ import annotations

import argparse
import csv
import json
import statistics
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


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


def as_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "1", "yes", "on"}:
            return True

        if normalized in {"false", "0", "no", "off"}:
            return False

    return None


def as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def distribution(values: list[Any]) -> dict[str, int]:
    counter: Counter[str] = Counter(
        "UNKNOWN" if value is None else str(value)
        for value in values
    )

    return dict(counter.most_common())


def metric(values: list[float]) -> dict[str, Any]:
    if not values:
        return {
            "count": 0,
            "min": None,
            "max": None,
            "mean": None,
            "median": None,
        }

    return {
        "count": len(values),
        "min": round(min(values), 4),
        "max": round(max(values), 4),
        "mean": round(statistics.fmean(values), 4),
        "median": round(statistics.median(values), 4),
    }


def pair_distribution(
    legacy_values: list[Any],
    rc3_values: list[Any],
) -> dict[str, int]:
    pairs = []

    for legacy, rc3 in zip(legacy_values, rc3_values):
        pairs.append(
            f"{legacy if legacy is not None else 'UNKNOWN'}"
            f" -> "
            f"{rc3 if rc3 is not None else 'UNKNOWN'}"
        )

    return distribution(pairs)


def build_report(
    rows: list[dict[str, Any]],
    session: Path,
) -> dict[str, Any]:
    legacy_actions = [
        nested(
            row,
            "comparison",
            "legacy",
            "action",
        )
        for row in rows
    ]
    rc3_actions = [
        nested(
            row,
            "comparison",
            "rc3_output",
            "action",
        )
        for row in rows
    ]
    legacy_scenarios = [
        nested(
            row,
            "comparison",
            "legacy",
            "selected_scenario",
        )
        for row in rows
    ]
    rc3_scenarios = [
        nested(
            row,
            "comparison",
            "rc3_output",
            "selected_scenario",
        )
        for row in rows
    ]
    action_matches = [
        as_bool(
            nested(
                row,
                "comparison",
                "comparison",
                "action_match",
            )
        )
        for row in rows
    ]
    scenario_matches = [
        as_bool(
            nested(
                row,
                "comparison",
                "comparison",
                "scenario_match",
            )
        )
        for row in rows
    ]
    confidences = [
        value
        for value in (
            as_float(
                nested(
                    row,
                    "comparison",
                    "rc3_output",
                    "confidence",
                )
            )
            for row in rows
        )
        if value is not None
    ]

    action_match_count = sum(
        1
        for value in action_matches
        if value is True
    )
    scenario_match_count = sum(
        1
        for value in scenario_matches
        if value is True
    )

    unsafe_flags = {
        "controller_authorized_true": sum(
            1
            for row in rows
            if as_bool(
                nested(
                    row,
                    "activation",
                    "controller_authorized",
                )
            )
            is True
        ),
        "controller_called_true": sum(
            1
            for row in rows
            if as_bool(
                nested(
                    row,
                    "activation",
                    "controller_called",
                )
            )
            is True
        ),
        "hardware_called_true": sum(
            1
            for row in rows
            if as_bool(
                nested(
                    row,
                    "activation",
                    "hardware_called",
                )
            )
            is True
        ),
    }

    sample_count = len(rows)

    return {
        "schema": "geocooling.rc34.shadow-analysis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": str(session),
        "sample_count": sample_count,
        "action_match": {
            "count": action_match_count,
            "rate": (
                round(action_match_count / sample_count, 4)
                if sample_count
                else 0.0
            ),
        },
        "scenario_match": {
            "count": scenario_match_count,
            "rate": (
                round(scenario_match_count / sample_count, 4)
                if sample_count
                else 0.0
            ),
        },
        "legacy_action_distribution": distribution(
            legacy_actions
        ),
        "rc3_action_distribution": distribution(
            rc3_actions
        ),
        "legacy_scenario_distribution": distribution(
            legacy_scenarios
        ),
        "rc3_scenario_distribution": distribution(
            rc3_scenarios
        ),
        "action_transition_matrix": pair_distribution(
            legacy_actions,
            rc3_actions,
        ),
        "scenario_transition_matrix": pair_distribution(
            legacy_scenarios,
            rc3_scenarios,
        ),
        "rc3_confidence": metric(confidences),
        "unsafe_flags": unsafe_flags,
        "shadow_safety_valid": all(
            count == 0
            for count in unsafe_flags.values()
        ),
        "readiness": {
            "minimum_samples": 100,
            "minimum_action_match_rate": 0.95,
            "minimum_scenario_match_rate": 0.90,
            "minimum_confidence_mean": 0.70,
            "enough_samples": sample_count >= 100,
            "action_match_ok": (
                action_match_count / sample_count >= 0.95
                if sample_count
                else False
            ),
            "scenario_match_ok": (
                scenario_match_count / sample_count >= 0.90
                if sample_count
                else False
            ),
            "confidence_ok": (
                report_mean(confidences) >= 0.70
                if confidences
                else False
            ),
            "safety_ok": all(
                count == 0
                for count in unsafe_flags.values()
            ),
        },
        "safety": {
            "analysis_only": True,
            "api_calls": False,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        },
    }


def report_mean(values: list[float]) -> float:
    return statistics.fmean(values) if values else 0.0


def markdown_table(
    headers: list[str],
    rows: list[list[Any]],
) -> str:
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
    readiness = report["readiness"]

    ready = all(
        [
            readiness["enough_samples"],
            readiness["action_match_ok"],
            readiness["scenario_match_ok"],
            readiness["confidence_ok"],
            readiness["safety_ok"],
        ]
    )

    markdown = f"""# RC3.4 — Analyse Shadow

**Session :** `{report["session"]}`  
**Échantillons :** {report["sample_count"]}  
**Généré le :** {report["generated_at"]}

## Résultat global

- Taux de correspondance des actions : **{report["action_match"]["rate"] * 100:.1f}%**
- Taux de correspondance des scénarios : **{report["scenario_match"]["rate"] * 100:.1f}%**
- Confiance RC3 moyenne : **{report["rc3_confidence"]["mean"]}**
- Sécurité SHADOW valide : **{report["shadow_safety_valid"]}**
- Prêt pour l’étape suivante : **{ready}**

## Critères de passage

| Critère | Seuil | Résultat | Conforme |
|---|---:|---:|---|
| Échantillons | ≥ {readiness["minimum_samples"]} | {report["sample_count"]} | {readiness["enough_samples"]} |
| Correspondance actions | ≥ {readiness["minimum_action_match_rate"] * 100:.0f}% | {report["action_match"]["rate"] * 100:.1f}% | {readiness["action_match_ok"]} |
| Correspondance scénarios | ≥ {readiness["minimum_scenario_match_rate"] * 100:.0f}% | {report["scenario_match"]["rate"] * 100:.1f}% | {readiness["scenario_match_ok"]} |
| Confiance moyenne | ≥ {readiness["minimum_confidence_mean"]:.2f} | {report["rc3_confidence"]["mean"]} | {readiness["confidence_ok"]} |
| Aucune activation | 0 incident | {sum(report["unsafe_flags"].values())} | {readiness["safety_ok"]} |

## Actions legacy

{markdown_table(
    ["Action", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["legacy_action_distribution"].items()
    ],
)}

## Actions RC3

{markdown_table(
    ["Action", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["rc3_action_distribution"].items()
    ],
)}

## Matrice des actions

{markdown_table(
    ["Legacy → RC3", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["action_transition_matrix"].items()
    ],
)}

## Matrice des scénarios

{markdown_table(
    ["Legacy → RC3", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["scenario_transition_matrix"].items()
    ],
)}

## Sécurité SHADOW

{markdown_table(
    ["Indicateur interdit", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["unsafe_flags"].items()
    ],
)}

## Interprétation

RC3 ne doit pas être raccordé au Controller tant que tous les critères de
passage ne sont pas atteints sur une période suffisamment représentative.
Les divergences restent utiles : elles permettent d’identifier les différences
entre la logique actuelle et le pipeline prédictif avant toute activation.

## Garanties

- analyse locale uniquement ;
- aucune API appelée ;
- aucune autorisation Controller ;
- aucune commande matérielle ;
- aucune publication MQTT ;
- aucune écriture dans la base applicative.
"""

    path.write_text(
        markdown,
        encoding="utf-8",
    )


def write_flat_csv(
    rows: list[dict[str, Any]],
    path: Path,
) -> None:
    columns = [
        "generated_at",
        "legacy_action",
        "rc3_action",
        "legacy_scenario",
        "rc3_scenario",
        "rc3_confidence",
        "action_match",
        "scenario_match",
        "controller_authorized",
        "controller_called",
        "hardware_called",
    ]

    with path.open(
        "w",
        newline="",
        encoding="utf-8",
    ) as stream:
        writer = csv.DictWriter(
            stream,
            fieldnames=columns,
        )
        writer.writeheader()

        for row in rows:
            writer.writerow(
                {
                    "generated_at": row.get(
                        "generated_at"
                    ),
                    "legacy_action": nested(
                        row,
                        "comparison",
                        "legacy",
                        "action",
                    ),
                    "rc3_action": nested(
                        row,
                        "comparison",
                        "rc3_output",
                        "action",
                    ),
                    "legacy_scenario": nested(
                        row,
                        "comparison",
                        "legacy",
                        "selected_scenario",
                    ),
                    "rc3_scenario": nested(
                        row,
                        "comparison",
                        "rc3_output",
                        "selected_scenario",
                    ),
                    "rc3_confidence": nested(
                        row,
                        "comparison",
                        "rc3_output",
                        "confidence",
                    ),
                    "action_match": nested(
                        row,
                        "comparison",
                        "comparison",
                        "action_match",
                    ),
                    "scenario_match": nested(
                        row,
                        "comparison",
                        "comparison",
                        "scenario_match",
                    ),
                    "controller_authorized": nested(
                        row,
                        "activation",
                        "controller_authorized",
                    ),
                    "controller_called": nested(
                        row,
                        "activation",
                        "controller_called",
                    ),
                    "hardware_called": nested(
                        row,
                        "activation",
                        "hardware_called",
                    ),
                }
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

    active = data_root / ".active-session"

    if active.exists():
        candidate = Path(
            active.read_text(
                encoding="utf-8",
            ).strip()
        )

        if candidate.exists():
            return candidate

    sessions = sorted(
        path
        for path in data_root.glob("session-*")
        if path.is_dir()
    )

    if not sessions:
        raise FileNotFoundError(
            "No RC3 shadow journal session found"
        )

    return sessions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="/opt/stacks/smart-building-controller/rc3-shadow-journal",
    )
    parser.add_argument("--session")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    session = resolve_session(
        data_root,
        args.session,
    )

    source = session / "shadow-comparisons.jsonl"

    if not source.exists():
        raise FileNotFoundError(source)

    rows = load_jsonl(source)
    report = build_report(
        rows,
        session,
    )

    output = session / "analysis"
    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    json_file = output / "analysis.json"
    md_file = output / "ANALYSIS.md"
    csv_file = output / "samples-flat.csv"

    json_file.write_text(
        json.dumps(
            report,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )
    write_markdown(
        report,
        md_file,
    )
    write_flat_csv(
        rows,
        csv_file,
    )

    print("============================================================")
    print(" RC3.4 — ANALYSE SHADOW TERMINÉE")
    print("============================================================")
    print("Session       :", session)
    print("Échantillons  :", report["sample_count"])
    print(
        "Action match  :",
        f'{report["action_match"]["rate"] * 100:.1f}%',
    )
    print(
        "Scenario match:",
        f'{report["scenario_match"]["rate"] * 100:.1f}%',
    )
    print(
        "Sécurité      :",
        report["shadow_safety_valid"],
    )
    print("Rapport       :", md_file)
    print("JSON          :", json_file)
    print("CSV           :", csv_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
