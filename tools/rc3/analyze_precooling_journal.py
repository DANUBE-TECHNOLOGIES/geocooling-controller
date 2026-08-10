#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any


def load_rows(path: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        payload = json.loads(line)
        if isinstance(payload, dict):
            rows.append(payload)
    return rows


def main() -> int:
    if len(sys.argv) != 2:
        print("usage: analyze_precooling_journal.py <precooling-snapshots.jsonl>", file=sys.stderr)
        return 2

    path = Path(sys.argv[1])
    rows = load_rows(path)
    if not rows:
        print("samples=0")
        return 0

    states: Counter[str] = Counter()
    confidences: list[float] = []
    avoided: list[float] = []
    leads: list[int] = []
    current_temperatures: list[float] = []

    for row in rows:
        advisory = row.get("advisory") if isinstance(row.get("advisory"), dict) else {}
        state = str(advisory.get("state") or "UNKNOWN")
        states[state] += 1

        forecast = advisory.get("forecast") if isinstance(advisory.get("forecast"), dict) else {}
        recommendation = advisory.get("recommendation") if isinstance(advisory.get("recommendation"), dict) else {}
        comfort = advisory.get("comfort") if isinstance(advisory.get("comfort"), dict) else {}

        confidence = forecast.get("confidence_at_crossing")
        if isinstance(confidence, (int, float)):
            confidences.append(float(confidence))

        delta = recommendation.get("predicted_avoided_temperature_c")
        if isinstance(delta, (int, float)):
            avoided.append(float(delta))

        lead = recommendation.get("lead_minutes")
        if isinstance(lead, int):
            leads.append(lead)

        current = comfort.get("current_indoor_temperature_c")
        if isinstance(current, (int, float)):
            current_temperatures.append(float(current))

    print(f"samples={len(rows)}")
    print("states=" + json.dumps(dict(states), ensure_ascii=False, sort_keys=True))
    print(f"average_confidence={mean(confidences):.3f}" if confidences else "average_confidence=none")
    print(f"average_predicted_avoided_c={mean(avoided):.3f}" if avoided else "average_predicted_avoided_c=none")
    print(f"average_lead_minutes={mean(leads):.1f}" if leads else "average_lead_minutes=none")
    print(f"current_indoor_min_c={min(current_temperatures):.3f}" if current_temperatures else "current_indoor_min_c=none")
    print(f"current_indoor_max_c={max(current_temperatures):.3f}" if current_temperatures else "current_indoor_max_c=none")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
