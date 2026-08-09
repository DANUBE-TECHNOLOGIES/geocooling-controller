#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.weather_inertia_predictor import (  # noqa: E402
    WeatherInertiaPredictor,
)

FILES = [
    REPO / "backend/app/geocooling/rc3/weather_inertia_predictor.py",
    REPO / "backend/app/geocooling/rc3/weather_inertia_live.py",
    REPO / "backend/app/geocooling/rc3/weather_inertia_router.py",
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

payload = WeatherInertiaPredictor().predict(
    context={
        "measurements": {
            "indoor_temperature_c": 25.2,
            "outdoor_temperature_c": 31.0,
            "floor_surface_temperature_c": 23.1,
        }
    },
    weather={
        "hourly": {
            "temperature_2m": [31.0] * 49,
            "cloud_cover": [25.0] * 49,
            "shortwave_radiation": [550.0] * 49,
        }
    },
)

assert payload["horizons_minutes"][-1] == 2880
assert payload["safety"]["controller_authorized"] is False

output = REPO / "audits" / "rc35-weather-inertia"
output.mkdir(parents=True, exist_ok=True)
report = output / "sample-prediction.json"
report.write_text(
    json.dumps(payload, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(payload, ensure_ascii=False, indent=2))
print()
print("RC3.5 backend validation: OK")
print("Controller authorization: false")
print("Report:", report)
