#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(REPO / "backend"))

from app.geocooling.rc3.contracts import (  # noqa: E402
    DecisionInput,
    DecisionMode,
)
from app.geocooling.rc3.defaults import (  # noqa: E402
    DefaultDecisionExplainer,
    DefaultScenarioGenerator,
    DescendingScenarioRanker,
    PassiveSafetyPolicy,
    PassiveScenarioEvaluator,
    StaticContextProvider,
)
from app.geocooling.rc3.pipeline import DecisionPipeline  # noqa: E402


FILES = [
    REPO / "backend/app/geocooling/rc3/contracts.py",
    REPO / "backend/app/geocooling/rc3/ports.py",
    REPO / "backend/app/geocooling/rc3/pipeline.py",
    REPO / "backend/app/geocooling/rc3/defaults.py",
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
    "post",
    "put",
    "patch",
    "delete",
}


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

        return 1

    pipeline = DecisionPipeline(
        context_provider=StaticContextProvider(
            DecisionInput.empty(
                mode=DecisionMode.PASSIVE,
            )
        ),
        scenario_generator=DefaultScenarioGenerator(),
        scenario_evaluator=PassiveScenarioEvaluator(),
        scenario_ranker=DescendingScenarioRanker(),
        decision_explainer=DefaultDecisionExplainer(),
        safety_policy=PassiveSafetyPolicy(),
    )

    result = pipeline.run()
    payload = result.as_dict()

    assert payload["controller_authorized"] is False
    assert payload["mode"] == "PASSIVE"
    assert payload["action"] == "WAIT"

    output = REPO / "audits" / "rc30-architecture-freeze"
    output.mkdir(parents=True, exist_ok=True)

    report = output / "sample-decision.json"
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
    print("RC3 security contract: OK")
    print("Controller authorization: false")
    print("Report:", report)

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
