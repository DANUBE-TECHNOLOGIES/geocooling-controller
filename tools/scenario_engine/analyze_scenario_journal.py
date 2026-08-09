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
from typing import Any


def nested(payload: dict[str, Any], *path: str) -> Any:
    current: Any = payload

    for key in path:
        if not isinstance(current, dict):
            return None

        current = current.get(key)

    return current


def as_float(value: Any) -> float | None:
    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if not math.isfinite(result):
        return None

    return result


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


def distribution(values: list[Any]) -> dict[str, int]:
    counter: Counter[str] = Counter(
        "UNKNOWN" if value is None else str(value)
        for value in values
    )

    return dict(counter.most_common())


def selected_scenario(row: dict[str, Any]) -> str | None:
    value = nested(
        row,
        "scenario_decision",
        "selected",
        "scenario",
    )

    return str(value) if value is not None else None


def context_action(row: dict[str, Any]) -> str | None:
    value = nested(
        row,
        "context",
        "recommendation",
        "action",
    )

    return str(value) if value is not None else None


def scenario_score(row: dict[str, Any]) -> float | None:
    return as_float(
        nested(
            row,
            "scenario_decision",
            "selected",
            "score",
        )
    )


def confidence(row: dict[str, Any]) -> float | None:
    return as_float(
        nested(
            row,
            "scenario_decision",
            "confidence",
        )
    )


def score_gap(row: dict[str, Any]) -> float | None:
    selected = scenario_score(row)
    alternatives = nested(
        row,
        "scenario_decision",
        "alternatives",
    )

    if selected is None or not isinstance(alternatives, list):
        return None

    alt_scores = [
        as_float(item.get("score"))
        for item in alternatives
        if isinstance(item, dict)
    ]
    alt_scores = [
        value
        for value in alt_scores
        if value is not None
    ]

    if not alt_scores:
        return None

    return selected - max(alt_scores)


def count_transitions(scenarios: list[str | None]) -> dict[str, Any]:
    clean = [
        scenario
        for scenario in scenarios
        if scenario is not None
    ]

    transitions = 0
    pairs: Counter[str] = Counter()

    for previous, current in zip(clean, clean[1:]):
        if previous != current:
            transitions += 1
            pairs[f"{previous} -> {current}"] += 1

    rate = (
        transitions / max(1, len(clean) - 1)
        if clean
        else 0.0
    )

    return {
        "count": transitions,
        "rate": round(rate, 4),
        "pairs": dict(pairs.most_common()),
    }


def disagreement(
    scenarios: list[str | None],
    actions: list[str | None],
) -> dict[str, Any]:
    pairs = [
        (scenario, action)
        for scenario, action in zip(scenarios, actions)
        if scenario is not None and action is not None
    ]

    disagreements = [
        pair
        for pair in pairs
        if not (
            (pair[0] == "WAIT" and pair[1] in {"WAIT", "BLOCKED"})
            or (
                pair[0] in {
                    "COOL_NOW",
                    "SOFT_COOLING",
                    "PRECOOL_30",
                    "PRECOOL_60",
                }
                and pair[1] in {
                    "START_COOLING",
                    "HOLD_COOLING",
                    "PRECOOL",
                }
            )
        )
    ]

    return {
        "comparable_samples": len(pairs),
        "disagreement_count": len(disagreements),
        "disagreement_rate": (
            round(len(disagreements) / len(pairs), 4)
            if pairs
            else 0.0
        ),
        "pairs": distribution(
            [f"{scenario} <> {action}" for scenario, action in disagreements]
        ),
    }


def build_report(
    rows: list[dict[str, Any]],
    session: Path,
) -> dict[str, Any]:
    scenarios = [
        selected_scenario(row)
        for row in rows
    ]
    actions = [
        context_action(row)
        for row in rows
    ]
    scores = [
        value
        for value in (
            scenario_score(row)
            for row in rows
        )
        if value is not None
    ]
    confidences = [
        value
        for value in (
            confidence(row)
            for row in rows
        )
        if value is not None
    ]
    gaps = [
        value
        for value in (
            score_gap(row)
            for row in rows
        )
        if value is not None
    ]
    energy = [
        value
        for value in (
            as_float(
                nested(
                    row,
                    "scenario_decision",
                    "selected",
                    "estimated_energy_kwh",
                )
            )
            for row in rows
        )
        if value is not None
    ]
    runtime = [
        value
        for value in (
            as_float(
                nested(
                    row,
                    "scenario_decision",
                    "selected",
                    "estimated_runtime_minutes",
                )
            )
            for row in rows
        )
        if value is not None
    ]

    low_gap_count = sum(
        1
        for value in gaps
        if value < 0.03
    )

    report = {
        "schema": "geocooling.rc21d.scenario-analysis.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "session": str(session),
        "sample_count": len(rows),
        "selected_scenario_distribution": distribution(scenarios),
        "context_action_distribution": distribution(actions),
        "selected_score": metric(scores),
        "decision_confidence": metric(confidences),
        "winner_score_gap": metric(gaps),
        "estimated_energy_kwh": metric(energy),
        "estimated_runtime_minutes": metric(runtime),
        "stability": count_transitions(scenarios),
        "decision_context_alignment": disagreement(
            scenarios,
            actions,
        ),
        "ambiguous_decisions": {
            "score_gap_below_0_03": low_gap_count,
            "rate": (
                round(low_gap_count / len(gaps), 4)
                if gaps
                else 0.0
            ),
        },
        "safety": {
            "read_only_analysis": True,
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
            "api_calls": False,
        },
    }

    return report


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
    metrics = [
        ("Score sélectionné", report["selected_score"]),
        ("Confiance", report["decision_confidence"]),
        ("Écart au 2e scénario", report["winner_score_gap"]),
        ("Énergie estimée", report["estimated_energy_kwh"]),
        ("Durée estimée", report["estimated_runtime_minutes"]),
    ]

    markdown = f"""# RC2.1D — Analyse des scénarios

**Session :** `{report["session"]}`  
**Échantillons :** {report["sample_count"]}  
**Généré le :** {report["generated_at"]}

## Scénarios sélectionnés

{markdown_table(
    ["Scénario", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["selected_scenario_distribution"].items()
    ],
)}

## Actions du Decision Context

{markdown_table(
    ["Action", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["context_action_distribution"].items()
    ],
)}

## Indicateurs

{markdown_table(
    ["Indicateur", "N", "Min", "Max", "Moyenne", "Médiane"],
    [
        [
            name,
            item["count"],
            item["min"],
            item["max"],
            item["mean"],
            item["median"],
        ]
        for name, item in metrics
    ],
)}

## Stabilité

- Changements de scénario : **{report["stability"]["count"]}**
- Taux de changement : **{report["stability"]["rate"] * 100:.1f}%**

{markdown_table(
    ["Transition", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["stability"]["pairs"].items()
    ],
)}

## Alignement avec le Decision Context

- Échantillons comparables : **{report["decision_context_alignment"]["comparable_samples"]}**
- Désaccords : **{report["decision_context_alignment"]["disagreement_count"]}**
- Taux de désaccord : **{report["decision_context_alignment"]["disagreement_rate"] * 100:.1f}%**

{markdown_table(
    ["Désaccord", "Occurrences"],
    [
        [name, count]
        for name, count
        in report["decision_context_alignment"]["pairs"].items()
    ],
)}

## Décisions ambiguës

- Écart inférieur à 0,03 : **{report["ambiguous_decisions"]["score_gap_below_0_03"]}**
- Taux : **{report["ambiguous_decisions"]["rate"] * 100:.1f}%**

## Interprétation

Un taux élevé de changements de scénario peut signaler un moteur trop sensible.
Un faible écart entre le premier et le deuxième scénario indique une décision
peu robuste. Les désaccords avec le Decision Context doivent être examinés avant
toute intégration du Scenario Engine dans le Brain opérationnel.

## Garanties

- analyse locale uniquement ;
- aucune API appelée ;
- aucun scénario activé ;
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
        "selected_scenario",
        "selected_score",
        "decision_confidence",
        "winner_score_gap",
        "context_action",
        "blocking",
        "risk_level",
        "estimated_energy_kwh",
        "estimated_runtime_minutes",
        "predicted_indoor_temperature_c",
        "indoor_temperature_c",
        "outdoor_temperature_c",
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
                    "generated_at": row.get("generated_at"),
                    "selected_scenario": selected_scenario(row),
                    "selected_score": scenario_score(row),
                    "decision_confidence": confidence(row),
                    "winner_score_gap": score_gap(row),
                    "context_action": context_action(row),
                    "blocking": nested(
                        row,
                        "context",
                        "blocking",
                    ),
                    "risk_level": nested(
                        row,
                        "context",
                        "highest_risk_level",
                    ),
                    "estimated_energy_kwh": nested(
                        row,
                        "scenario_decision",
                        "selected",
                        "estimated_energy_kwh",
                    ),
                    "estimated_runtime_minutes": nested(
                        row,
                        "scenario_decision",
                        "selected",
                        "estimated_runtime_minutes",
                    ),
                    "predicted_indoor_temperature_c": nested(
                        row,
                        "scenario_decision",
                        "selected",
                        "predicted_indoor_temperature_c",
                    ),
                    "indoor_temperature_c": nested(
                        row,
                        "context",
                        "measurements",
                        "indoor_temperature_c",
                    ),
                    "outdoor_temperature_c": nested(
                        row,
                        "context",
                        "measurements",
                        "outdoor_temperature_c",
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
            "No scenario journal session found"
        )

    return sessions[-1]


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--data-root",
        default="/opt/stacks/smart-building-controller/scenario-journal",
    )
    parser.add_argument("--session")
    args = parser.parse_args()

    data_root = Path(args.data_root)
    session = resolve_session(
        data_root,
        args.session,
    )

    source = session / "scenario-decisions.jsonl"

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
    print(" RC2.1D — ANALYSE TERMINÉE")
    print("============================================================")
    print("Session      :", session)
    print("Échantillons :", len(rows))
    print("Transitions  :", report["stability"]["count"])
    print(
        "Désaccords   :",
        report["decision_context_alignment"]["disagreement_count"],
    )
    print("Rapport      :", md_file)
    print("JSON         :", json_file)
    print("CSV          :", csv_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
