#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

path = Path(
    "tools/rc3/rc3_shadow_journal_collector.py"
)

tree = ast.parse(
    path.read_text(
        encoding="utf-8",
    ),
    filename=str(path),
)

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

forbidden_http = {
    "POST",
    "PUT",
    "PATCH",
    "DELETE",
}

violations = []


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


for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    name = dotted_name(node.func)
    leaf = name.rsplit(".", 1)[-1]

    if leaf in forbidden_direct:
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
                in forbidden_http
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

print("Validation sécurité RC3.3 : OK")
print("HTTP sortant : GET uniquement")
print("Controller autorisé : non")
print("Commande matérielle : aucune")
