#!/usr/bin/env python3
from __future__ import annotations

import ast
import sys
from pathlib import Path

REPO = Path(__file__).resolve().parents[2]

FILES = [
    REPO / "backend/app/geocooling/decision_context_live_v1.py",
    REPO / "backend/app/geocooling/decision_context_live_router_v1.py",
]

FORBIDDEN_CALLS = {
    "write_coil",
    "set_relay",
    "relay_on",
    "relay_off",
    "publish",
}

FORBIDDEN_HTTP_METHODS = {
    "post",
    "put",
    "patch",
    "delete",
}


def dotted_name(node: ast.AST) -> str | None:
    if isinstance(node, ast.Name):
        return node.id

    if isinstance(node, ast.Attribute):
        base = dotted_name(node.value)

        if base:
            return f"{base}.{node.attr}"

        return node.attr

    return None


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

            name = dotted_name(node.func) or ""
            leaf = name.rsplit(".", 1)[-1]

            if leaf in FORBIDDEN_CALLS:
                violations.append(
                    f"{path}:{node.lineno}:{name}"
                )

            if leaf in FORBIDDEN_HTTP_METHODS:
                # FastAPI decorators such as router.get are harmless here;
                # only outbound client calls are forbidden.
                owner = name.rsplit(".", 1)[0] if "." in name else ""

                if owner not in {"router"}:
                    violations.append(
                        f"{path}:{node.lineno}:{name}"
                    )

        text = path.read_text(encoding="utf-8")

        for token in (
            'method="POST"',
            'method="PUT"',
            'method="PATCH"',
            'method="DELETE"',
        ):
            if token in text:
                violations.append(
                    f"{path}: forbidden request method token {token}"
                )

    if violations:
        print("Security violations:")

        for violation in violations:
            print(" -", violation)

        return 1

    print("RC1.7C security contract: OK")
    print("Outbound HTTP method: GET only")
    print("Hardware write: none")
    print("MQTT publish: none")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
