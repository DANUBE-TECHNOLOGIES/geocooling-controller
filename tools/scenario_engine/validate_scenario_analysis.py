#!/usr/bin/env python3
from __future__ import annotations

import ast
from pathlib import Path

path = Path(
    "tools/scenario_engine/analyze_scenario_journal.py"
)

tree = ast.parse(
    path.read_text(
        encoding="utf-8",
    ),
    filename=str(path),
)

forbidden = {
    "write_coil",
    "write_coils",
    "write_register",
    "write_registers",
    "set_relay",
    "relay_on",
    "relay_off",
    "publish",
    "post",
    "put",
    "patch",
    "delete",
    "urlopen",
}

violations = []

for node in ast.walk(tree):
    if not isinstance(node, ast.Call):
        continue

    if isinstance(node.func, ast.Attribute):
        leaf = node.func.attr
    elif isinstance(node.func, ast.Name):
        leaf = node.func.id
    else:
        leaf = ""

    if leaf in forbidden:
        violations.append(
            f"{path}:{getattr(node, 'lineno', '?')}:{leaf}"
        )

if violations:
    print("ERREUR : primitive interdite détectée")

    for violation in violations:
        print(" -", violation)

    raise SystemExit(1)

print("Validation sécurité RC2.1D : OK")
print("Analyse locale uniquement")
print("Aucune API")
print("Aucune commande matérielle")
