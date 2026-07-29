from __future__ import annotations

import ast
from pathlib import Path


TARGET = Path("backend/app/geocooling/industrial_platform.py")


def test_c0201r2_platform_imports_digital_twin():
    source = TARGET.read_text(encoding="utf-8")
    assert (
        "from app.geocooling.digital_twin import GeoCoolingDigitalTwin"
        in source
    )


def test_c0201r2_platform_initializes_digital_twin():
    source = TARGET.read_text(encoding="utf-8")
    tree = ast.parse(source)

    platform_class = next(
        node
        for node in tree.body
        if isinstance(node, ast.ClassDef)
        and node.name == "GeoCoolingIndustrialPlatform"
    )
    init_node = next(
        node
        for node in platform_class.body
        if isinstance(node, ast.FunctionDef)
        and node.name == "__init__"
    )

    assignments = [
        node
        for node in ast.walk(init_node)
        if isinstance(node, ast.Assign)
    ]

    found = False
    for assignment in assignments:
        for target in assignment.targets:
            if (
                isinstance(target, ast.Attribute)
                and isinstance(target.value, ast.Name)
                and target.value.id == "self"
                and target.attr == "digital_twin"
                and isinstance(assignment.value, ast.Call)
                and isinstance(assignment.value.func, ast.Name)
                and assignment.value.func.id == "GeoCoolingDigitalTwin"
            ):
                found = True

    assert found is True
