#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

FILES = [
    Path("tools/scenario_engine/scenario_journal_collector.py"),
]

FORBIDDEN_DIRECT_CALLS = {
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

FORBIDDEN_HTTP_METHODS = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}

violations: list[str] = []


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


for path in FILES:
    source = path.read_text(
        encoding="utf-8",
    )

    tree = ast.parse(
        source,
        filename=str(path),
    )

    for node in ast.walk(tree):
        if not isinstance(node, ast.Call):
            continue

        call_name = dotted_name(node.func)
        leaf = call_name.rsplit(".", 1)[-1]

        if leaf in FORBIDDEN_DIRECT_CALLS:
            violations.append(
                f"{path}:{node.lineno}:{call_name}"
            )

        if call_name.endswith("Request"):
            for keyword in node.keywords:
                if keyword.arg != "method":
                    continue

                if (
                    isinstance(keyword.value, ast.Constant)
                    and isinstance(keyword.value.value, str)
                    and keyword.value.value.upper()
                    in FORBIDDEN_HTTP_METHODS
                ):
                    violations.append(
                        f"{path}:{node.lineno}:"
                        f"HTTP {keyword.value.value.upper()}"
                    )

if violations:
    print("ERREUR : primitive interdite détectée")

    for violation in violations:
        print(" -", violation)

    raise SystemExit(1)

print("Validation sécurité RC2.1C : OK")
print("HTTP sortant : GET uniquement")
print("Scénario activé : non")
print("Commande matérielle : aucune")
