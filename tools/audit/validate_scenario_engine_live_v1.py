#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.scenario_engine_live_v1 import (  # noqa: E402
    LiveScenarioEngineService,
)


class FakeContextService:
    def build_live_context(self, configuration=None):
        return {
            "blocking": False,
            "measurements": {
                "indoor_temperature_c": 25.7,
            },
            "configuration": {
                "comfort_target_c": 24.0,
                "condensation_margin_c": 4.2,
                "minimum_condensation_margin_c": 3.0,
            },
            "recommendation": {
                "confidence": 0.82,
            },
            "forecasts": [
                {
                    "horizon_minutes": 120,
                    "indoor_temperature_c": 26.3,
                    "confidence": 0.80,
                    "source": "validation",
                }
            ],
            "live_sources": {},
        }

    def source_status(self):
        return {
            "sources": {
                "thermal": {"available": True},
                "weather": {"available": True},
                "prediction": {"available": True},
            }
        }


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)
        return f"{parent}.{node.attr}" if parent else node.attr

    return ""


def security_check() -> None:
    files = [
        REPO / "backend/app/geocooling/scenario_engine_live_v1.py",
        REPO / "backend/app/geocooling/scenario_engine_live_router_v1.py",
    ]

    forbidden_direct = {
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

            if leaf in forbidden_direct:
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
        print("ERREUR : primitive interdite détectée")

        for violation in violations:
            print(" -", violation)

        raise SystemExit(1)


def main() -> int:
    security_check()

    service = LiveScenarioEngineService(
        context_service=FakeContextService(),
    )
    payload = service.evaluate_live()

    assert payload["mode"] == "passive"
    assert payload["activation"]["hardware_called"] is False
    assert payload["activation"]["controller_called"] is False

    output = REPO / "audits" / "rc21b-live-scenario"
    output.mkdir(parents=True, exist_ok=True)

    report = output / "sample-live-evaluation.json"
    report.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("Validation sécurité : OK")
    print("Rapport :", report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
