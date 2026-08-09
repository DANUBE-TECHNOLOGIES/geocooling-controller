#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.shadow import (  # noqa: E402
    ShadowDecisionService,
)

FILES = [
    REPO / "backend/app/geocooling/rc3/adapters.py",
    REPO / "backend/app/geocooling/rc3/shadow.py",
    REPO / "backend/app/geocooling/rc3/router.py",
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
    "urlopen",
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
    print("ERREUR : primitive interdite détectée")

    for violation in violations:
        print(" -", violation)

    raise SystemExit(1)

result = ShadowDecisionService().compare(
    context_payload={
        "schema": "geocooling.decision-context.v1",
        "recommendation": {
            "action": "WAIT",
        },
        "measurements": {
            "indoor_temperature_c": 24.1,
        },
        "configuration": {},
        "risks": [],
    },
    scenario_payload={
        "schema": "geocooling.rc21.scenario-decision.v1",
        "selected": {
            "scenario": "WAIT",
            "score": 0.8,
            "comfort_score": 0.8,
            "safety_score": 1.0,
            "energy_score": 1.0,
            "stability_score": 0.9,
            "learning_score": 0.5,
            "estimated_runtime_minutes": 0,
            "estimated_energy_kwh": 0.0,
            "reasons": [],
        },
        "alternatives": [],
    },
).as_dict()

assert result["rc3_output"]["mode"] == "SHADOW"
assert (
    result["rc3_output"]["controller_authorized"]
    is False
)

output = REPO / "audits" / "rc31-shadow-pipeline"
output.mkdir(parents=True, exist_ok=True)

report = output / "sample-shadow-comparison.json"
report.write_text(
    json.dumps(result, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

print(json.dumps(result, ensure_ascii=False, indent=2))
print()
print("RC3.1 security contract: OK")
print("Controller authorization: false")
print("Report:", report)
