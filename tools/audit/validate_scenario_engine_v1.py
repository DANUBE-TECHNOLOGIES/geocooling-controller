#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.scenario_engine_v1 import (  # noqa: E402
    ScenarioEngine,
)


def security_check() -> None:
    files = [
        REPO / "backend/app/geocooling/scenario_engine_v1.py",
        REPO / "backend/app/geocooling/scenario_engine_router_v1.py",
    ]

    forbidden_calls = {
        "write_coil",
        "write_coils",
        "write_register",
        "write_registers",
        "set_relay",
        "relay_on",
        "relay_off",
        "publish",
    }

    forbidden_http_owners = {
        "requests",
        "httpx",
        "session",
        "client",
        "api_client",
        "http_client",
    }

    forbidden_http_methods = {
        "post",
        "put",
        "patch",
        "delete",
    }

    violations = []

    def dotted_name(node: ast.AST) -> str:
        if isinstance(node, ast.Name):
            return node.id

        if isinstance(node, ast.Attribute):
            parent = dotted_name(node.value)
            return f"{parent}.{node.attr}" if parent else node.attr

        return ""

    for path in files:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = dotted_name(node.func)
            leaf = name.rsplit(".", 1)[-1]
            owner = (
                name.rsplit(".", 1)[0]
                if "." in name
                else ""
            )
            root_owner = owner.split(".", 1)[0]

            if leaf in forbidden_calls:
                violations.append(
                    f"{path}:{node.lineno}:{name}"
                )

            if (
                leaf in forbidden_http_methods
                and root_owner in forbidden_http_owners
            ):
                violations.append(
                    f"{path}:{node.lineno}:{name}"
                )

    if violations:
        print("Security violations:")
        for violation in violations:
            print(" -", violation)
        raise SystemExit(1)


def main() -> int:
    security_check()

    context = {
        "blocking": False,
        "measurements": {
            "indoor_temperature_c": 25.6,
        },
        "configuration": {
            "comfort_target_c": 24.0,
            "condensation_margin_c": 4.3,
            "minimum_condensation_margin_c": 3.0,
        },
        "recommendation": {
            "confidence": 0.82,
        },
        "forecasts": [
            {
                "horizon_minutes": 120,
                "indoor_temperature_c": 26.2,
                "confidence": 0.80,
                "source": "validation",
            }
        ],
    }

    result = ScenarioEngine().evaluate(context).as_dict()

    output = REPO / "audits" / "rc21-scenario-engine"
    output.mkdir(parents=True, exist_ok=True)

    report = output / "sample-decision.json"
    report.write_text(
        json.dumps(result, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(result, ensure_ascii=False, indent=2))
    print()
    print("Security contract: OK")
    print("Report:", report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
