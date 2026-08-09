#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.prediction_validation import (  # noqa: E402
    PredictionValidationEngine,
)

FILES = [
    REPO / "backend/app/geocooling/rc3/prediction_validation.py",
    REPO / "backend/app/geocooling/rc3/prediction_validation_live.py",
    REPO / "backend/app/geocooling/rc3/prediction_validation_router.py",
    REPO / "tools/rc3/rc37_prediction_collector.py",
]

FORBIDDEN = {
    "write_coil",
    "write_coils",
    "write_register",
    "write_registers",
    "set_relay",
    "relay_on",
    "relay_off",
    "publish",
    "send",
    "sendall",
}

violations = []

for path in FILES:
    tree = ast.parse(
        path.read_text(encoding="utf-8"),
        filename=str(path),
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        if isinstance(node.func, ast.Attribute):
            leaf = node.func.attr
        elif isinstance(node.func, ast.Name):
            leaf = node.func.id
        else:
            leaf = ""

        if leaf in FORBIDDEN:
            violations.append(
                f"{path}:{node.lineno}:{leaf}"
            )

if violations:
    print("ERREUR : primitive interdite")
    for violation in violations:
        print(" -", violation)
    raise SystemExit(1)

report = PredictionValidationEngine(
    tolerance_minutes=5,
).validate(
    [
        {
            "captured_at": "2026-08-03T12:00:00+00:00",
            "context": {
                "measurements": {
                    "indoor_temperature_c": 25.0,
                }
            },
            "prediction": {
                "trajectories": [
                    {
                        "scenario": "BASELINE",
                        "points": [
                            {
                                "horizon_minutes": 60,
                                "predicted_indoor_temperature_c": 25.5,
                            }
                        ],
                    }
                ]
            },
        },
        {
            "captured_at": "2026-08-03T13:00:00+00:00",
            "context": {
                "measurements": {
                    "indoor_temperature_c": 25.3,
                }
            },
            "prediction": {
                "trajectories": [],
            },
        },
    ]
)

assert report["match_count"] == 1
assert report["safety"]["controller_authorized"] is False

output = REPO / "audits" / "rc37-prediction-validation"
output.mkdir(parents=True, exist_ok=True)
path = output / "sample-report.json"
path.write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(report, ensure_ascii=False, indent=2))
print()
print("RC3.7 validation: OK")
print("Controller authorization: false")
