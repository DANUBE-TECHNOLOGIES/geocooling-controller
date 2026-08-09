#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.predictor_calibration import (  # noqa: E402
    CalibrationSample,
    PredictorCalibrationEngine,
)

FILES = [
    REPO / "backend/app/geocooling/rc3/predictor_calibration.py",
    REPO / "backend/app/geocooling/rc3/predictor_calibration_live.py",
    REPO / "backend/app/geocooling/rc3/predictor_calibration_router.py",
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

samples = tuple(
    CalibrationSample(
        horizon_minutes=60 if index < 10 else 720,
        predicted_c=25.3,
        actual_c=25.0,
        error_c=0.3,
    )
    for index in range(20)
)

payload = PredictorCalibrationEngine().calibrate(
    current_model={
        "fast_time_constant_hours": 2.5,
        "slow_time_constant_hours": 18.0,
        "mass_coupling": 0.28,
        "solar_gain_c_per_hour_at_full_sun": 0.20,
        "soft_cooling_c_per_hour": 0.28,
        "full_cooling_c_per_hour": 0.52,
        "model_confidence": 0.62,
    },
    samples=samples,
)

assert payload["activation"]["automatic"] is False
assert payload["safety"]["controller_authorized"] is False

output = REPO / "audits" / "rc36-calibration"
output.mkdir(parents=True, exist_ok=True)
report = output / "sample-calibration.json"
report.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(payload, ensure_ascii=False, indent=2))
print()
print("RC3.6 validation: OK")
print("Automatic activation: false")
print("Report:", report)
