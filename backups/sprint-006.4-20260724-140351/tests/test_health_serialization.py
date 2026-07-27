from __future__ import annotations

import ast
from pathlib import Path


def test_health_uses_jsonable_encoder() -> None:
    source = Path("backend/app/main.py").read_text(encoding="utf-8")
    tree = ast.parse(source)

    imported = any(
        isinstance(node, ast.ImportFrom)
        and node.module == "fastapi.encoders"
        and any(alias.name == "jsonable_encoder" for alias in node.names)
        for node in tree.body
    )
    assert imported, "jsonable_encoder n'est pas importé"

    health = next(
        node for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
        and node.name == "health"
    )

    calls = [node for node in ast.walk(health) if isinstance(node, ast.Call)]
    assert any(
        isinstance(call.func, ast.Name) and call.func.id == "jsonable_encoder"
        for call in calls
    ), "Le endpoint /health n'encode pas récursivement son contenu"
