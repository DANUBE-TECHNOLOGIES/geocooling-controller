#!/usr/bin/env python3
from __future__ import annotations
import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.validation_calibration_bridge import (
    ValidationCalibrationBridge,
)

files = [
    REPO / "backend/app/geocooling/rc3/validation_calibration_bridge.py",
    REPO / "backend/app/geocooling/rc3/validation_calibration_bridge_live.py",
    REPO / "backend/app/geocooling/rc3/validation_calibration_bridge_router.py",
]

forbidden = {
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

for path in files:
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

        if leaf in forbidden:
            violations.append(
                f"{path}:{node.lineno}:{leaf}"
            )

if violations:
    print("ERREUR : primitive interdite")
    for violation in violations:
        print(" -", violation)
    raise SystemExit(1)

sample = ValidationCalibrationBridge.sample_from_match(
    {
        "horizon_minutes": 60,
        "predicted_indoor_temperature_c": 25.5,
        "actual_indoor_temperature_c": 25.2,
    }
)

assert sample is not None

payload = {
    "schema": "geocooling.rc38.validation.v1",
    "sample": {
        "horizon_minutes": sample.horizon_minutes,
        "predicted_c": sample.predicted_c,
        "actual_c": sample.actual_c,
        "error_c": round(sample.error_c, 4),
    },
    "automatic_activation": False,
    "controller_authorized": False,
}

output = REPO / "audits/rc38-validation-calibration"
output.mkdir(parents=True, exist_ok=True)
(output / "sample-validation.json").write_text(
    json.dumps(payload, indent=2),
    encoding="utf-8",
)

print(json.dumps(payload, indent=2))
print("RC3.8 validation: OK")
