#!/usr/bin/env python3
from __future__ import annotations

import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.decision_context_builder_v1 import (  # noqa: E402
    PassiveDecisionContextBuilder,
)


def main() -> int:
    context = PassiveDecisionContextBuilder().build(
        thermal={
            "indoor_temperature": 25.3,
            "indoor_humidity": 54.0,
            "dew_point": 15.4,
            "floor_surface_temperature": 21.5,
            "condensation_margin": 6.1,
        },
        weather={
            "outdoor_temperature": 29.7,
        },
        prediction={
            "predicted_temperature_2h": 25.9,
            "predicted_temperature_4h": 26.4,
            "confidence": 0.74,
        },
        historian={
            "available": True,
        },
        learning=None,
        hardware={
            "ready": False,
        },
        configuration={
            "comfort_target_c": 24.0,
            "cooling_start_threshold_c": 25.0,
            "cooling_stop_threshold_c": 23.8,
            "minimum_condensation_margin_c": 3.0,
        },
    )

    payload = context.as_dict()

    assert payload["metadata"]["mode"] == "passive"
    assert payload["availability"]["hardware"] is False
    assert payload["recommendation"]["action"] == "WAIT"
    assert payload["blocking"] is False

    output_dir = REPO / "audits" / "rc17b-context-builder"
    output_dir.mkdir(parents=True, exist_ok=True)

    output_file = output_dir / "sample-context.json"
    output_file.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("Report:", output_file)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
