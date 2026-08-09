#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.live_shadow import (  # noqa: E402
    LiveShadowRunner,
)


class FakeClient:
    def get_json(self, route):
        if route == "/geocooling/decision-context/live":
            return {
                "schema": "geocooling.decision-context.v1",
                "timestamp": "2026-08-03T12:00:00+00:00",
                "measurements": {
                    "indoor_temperature_c": 25.4,
                },
                "configuration": {},
                "recommendation": {
                    "action": "WAIT",
                },
                "risks": [],
            }

        if route == "/geocooling/scenario-engine/live":
            return {
                "scenario_decision": {
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
                }
            }

        raise RuntimeError(route)


FILES = [
    REPO / "backend/app/geocooling/rc3/live_shadow.py",
    REPO / "backend/app/geocooling/rc3/live_shadow_router.py",
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

FORBIDDEN_HTTP = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}


def dotted_name(node: ast.AST) -> str:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        parent = dotted_name(node.value)

        return (
            f"{parent}.{node.attr}"
            if parent
            else node.attr
        )

    return ""


def main() -> int:
    violations = []

    for path in FILES:
        tree = ast.parse(
            path.read_text(encoding="utf-8"),
            filename=str(path),
        )

        for node in ast.walk(tree):
            if not isinstance(node, ast.Call):
                continue

            name = dotted_name(node.func)
            leaf = name.rsplit(".", 1)[-1]

            if leaf in FORBIDDEN:
                violations.append(
                    f"{path}:{node.lineno}:{name}"
                )

            if name.endswith("Request"):
                for keyword in node.keywords:
                    if keyword.arg != "method":
                        continue

                    if (
                        isinstance(
                            keyword.value,
                            ast.Constant,
                        )
                        and isinstance(
                            keyword.value.value,
                            str,
                        )
                        and keyword.value.value.upper()
                        in FORBIDDEN_HTTP
                    ):
                        violations.append(
                            f"{path}:{node.lineno}:"
                            f"HTTP {keyword.value.value.upper()}"
                        )

    if violations:
        print("ERREUR : primitive interdite détectée")

        for violation in violations:
            print(" -", violation)

        return 1

    payload = LiveShadowRunner(
        client=FakeClient(),
    ).run()

    assert (
        payload["activation"]["controller_authorized"]
        is False
    )
    assert (
        payload["activation"]["hardware_called"]
        is False
    )
    assert (
        payload["safety"]["outbound_http_methods"]
        == ["GET"]
    )

    output = REPO / "audits" / "rc32-live-shadow"
    output.mkdir(
        parents=True,
        exist_ok=True,
    )

    report = output / "sample-live-shadow.json"
    report.write_text(
        json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )

    print(json.dumps(payload, ensure_ascii=False, indent=2))
    print()
    print("RC3.2 security contract: OK")
    print("Controller authorization: false")
    print("Report:", report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
