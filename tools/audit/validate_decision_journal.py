#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

FILES = [
    Path("tools/audit/decision_journal_collector.py"),
]

FORBIDDEN = {
    "post",
    "put",
    "patch",
    "delete",
    "publish",
    "write_coil",
    "set_relay",
    "relay_on",
    "relay_off",
}

violations = []

for path in FILES:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))

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
            violations.append(f"{path}:{node.lineno}:{leaf}")

    text = path.read_text(encoding="utf-8")

    for token in ('method="POST"', 'method="PUT"', 'method="PATCH"', 'method="DELETE"'):
        if token in text:
            violations.append(f"{path}: forbidden token {token}")

if violations:
    print("ERREUR : primitive interdite détectée")
    for violation in violations:
        print(" -", violation)
    raise SystemExit(1)

print("Validation sécurité RC1.7D : OK")
print("HTTP sortant : GET uniquement")
print("Commandes matérielles : aucune")
