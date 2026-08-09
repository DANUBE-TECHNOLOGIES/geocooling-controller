#!/usr/bin/env python3
from __future__ import annotations

import ast
import json
import os
import re
import subprocess
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
BACKEND = ROOT / "backend"
FRONTEND = ROOT / "frontend"
STAMP = datetime.now().strftime("%Y%m%d-%H%M%S")
OUT = ROOT / "audits" / f"dependency-{STAMP}"

IGNORED = {
    ".git", ".next", "node_modules", "__pycache__", ".pytest_cache",
    ".mypy_cache", ".ruff_cache", ".venv", "venv", ".venv-test",
    "venv-test", "backups", "audits", "dist", "build", "coverage",
    "payload",
}

FAMILIES = {
    "brain": ("brain",),
    "weather": ("weather",),
    "prediction": ("predict", "forecast"),
    "learning": ("learn", "adaptive"),
    "thermal": ("thermal",),
    "historian": ("histor",),
    "digital_twin": ("digital_twin",),
    "safety": ("safety", "gate"),
    "controller": ("controller",),
    "hardware": ("hardware", "waveshare", "modbus", "relay"),
    "mqtt": ("mqtt",),
    "runtime": ("runtime",),
}

ROUTE_RE = re.compile(
    r'@\s*(?:app|router)\.(get|post|put|patch|delete)'
    r'\s*\(\s*["\']([^"\']+)["\']',
    re.I,
)

PREFIX_RE = re.compile(
    r'APIRouter\s*\([^)]*prefix\s*=\s*["\']([^"\']+)["\']',
    re.S,
)

API_RES = [
    re.compile(r'fetch\s*\(\s*[`"\']([^`"\']+)'),
    re.compile(r'axios\.(?:get|post|put|patch|delete)\s*\(\s*[`"\']([^`"\']+)'),
    re.compile(r'[`"\'](/api/[^`"\' ?]+)'),
]


def run(command):
    try:
        result = subprocess.run(
            command,
            cwd=ROOT,
            capture_output=True,
            text=True,
            timeout=30,
            check=False,
        )
        return {
            "returncode": result.returncode,
            "stdout": result.stdout.strip(),
            "stderr": result.stderr.strip(),
        }
    except Exception as exc:
        return {
            "returncode": 999,
            "stdout": "",
            "stderr": str(exc),
        }


def ignored(path: Path) -> bool:
    rel = path.relative_to(ROOT)
    for part in rel.parts:
        if part in IGNORED:
            return True
        if part.startswith("release-") or part.startswith("backup-"):
            return True
    return False


def files(root: Path, suffixes: set[str]):
    if not root.exists():
        return
    for current, directories, names in os.walk(root):
        current_path = Path(current)
        directories[:] = [
            name
            for name in directories
            if not ignored(current_path / name)
        ]
        for name in names:
            path = current_path / name
            if not ignored(path) and path.suffix in suffixes:
                yield path


def read(path: Path) -> str:
    try:
        return path.read_text(encoding="utf-8")
    except UnicodeDecodeError:
        return path.read_text(encoding="utf-8", errors="replace")
    except Exception:
        return ""


def rel(path: Path) -> str:
    return str(path.relative_to(ROOT))


def module_name(path: Path) -> str:
    parts = list(path.relative_to(BACKEND).with_suffix("").parts)
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def families_for(module: str, file: str):
    value = f"{module} {file}".lower()
    return sorted(
        family
        for family, tokens in FAMILIES.items()
        if any(token in value for token in tokens)
    )


python_files = sorted(files(BACKEND, {".py"}))
frontend_files = sorted(files(FRONTEND, {".ts", ".tsx", ".js", ".jsx", ".mjs", ".cjs"}))

module_files = {}
trees = {}
syntax_errors = []

for path in python_files:
    module = module_name(path)
    module_files[module] = rel(path)
    try:
        trees[module] = ast.parse(read(path), filename=rel(path))
    except SyntaxError as exc:
        syntax_errors.append({
            "file": rel(path),
            "line": exc.lineno,
            "message": exc.msg,
        })

raw_imports = defaultdict(set)
classes = defaultdict(list)
functions = defaultdict(list)
routes = []

for module, tree in trees.items():
    file = module_files[module]
    text = read(ROOT / file)
    prefix_match = PREFIX_RE.search(text)
    prefix = prefix_match.group(1).rstrip("/") if prefix_match else ""

    for match in ROUTE_RE.finditer(text):
        path = match.group(2)
        full_path = prefix + path if prefix else path
        routes.append({
            "method": match.group(1).upper(),
            "path": full_path,
            "file": file,
            "line": text[:match.start()].count("\n") + 1,
        })

    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            for alias in node.names:
                raw_imports[module].add(alias.name)
        elif isinstance(node, ast.ImportFrom):
            if node.module:
                raw_imports[module].add(node.module)
        elif isinstance(node, ast.ClassDef):
            classes[module].append(node.name)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            functions[module].append(node.name)

known = set(module_files)
edges = defaultdict(set)
imported_by = defaultdict(set)
external = defaultdict(set)

for source, imports in raw_imports.items():
    for imported in imports:
        candidates = [imported]
        if imported.startswith("app."):
            candidates.append(imported.removeprefix("app."))
        else:
            candidates.append("app." + imported)

        target = next((candidate for candidate in candidates if candidate in known), None)

        if target is None:
            matches = [
                item
                for item in known
                if any(item.startswith(candidate + ".") for candidate in candidates)
            ]
            if len(matches) == 1:
                target = matches[0]

        if target:
            edges[source].add(target)
            imported_by[target].add(source)
        else:
            external[source].add(imported)

nodes = {}

for module, file in module_files.items():
    nodes[module] = {
        "module": module,
        "file": file,
        "families": families_for(module, file),
        "imports": sorted(edges.get(module, set())),
        "imported_by": sorted(imported_by.get(module, set())),
        "classes": sorted(classes.get(module, [])),
        "functions": sorted(functions.get(module, [])),
        "lines": len(read(ROOT / file).splitlines()),
    }

orphans = [
    node
    for node in nodes.values()
    if not node["imported_by"]
    and node["module"] not in {"app.main", "main"}
    and not node["file"].endswith("/__init__.py")
]

duplicate_classes = defaultdict(list)
for module, names in classes.items():
    for name in names:
        duplicate_classes[name].append({
            "module": module,
            "file": module_files[module],
        })

duplicate_classes = {
    name: values
    for name, values in duplicate_classes.items()
    if len(values) > 1
}

frontend_calls = []
for path in frontend_files:
    text = read(path)
    seen = set()
    for pattern in API_RES:
        for match in pattern.finditer(text):
            value = match.group(1).split("?", 1)[0]
            if value in seen:
                continue
            seen.add(value)
            frontend_calls.append({
                "path": value,
                "file": rel(path),
                "line": text[:match.start()].count("\n") + 1,
            })

backend_paths = {route["path"] for route in routes}
missing_calls = []

for call in frontend_calls:
    value = call["path"]
    if not value.startswith("/api/geocooling"):
        continue
    expected = value.removeprefix("/api")
    if not any(
        expected == route
        or expected.startswith(route.rstrip("/") + "/")
        or route.startswith(expected.rstrip("/") + "/")
        for route in backend_paths
    ):
        missing_calls.append(call)

family_modules = defaultdict(list)
for node in nodes.values():
    for family in node["families"]:
        family_modules[family].append(node)

central = sorted(
    nodes.values(),
    key=lambda item: (
        len(item["imported_by"]) + len(item["imports"]),
        len(item["imported_by"]),
    ),
    reverse=True,
)

git = {
    "branch": run(["git", "branch", "--show-current"]),
    "status": run(["git", "status", "--short"]),
    "commit": run(["git", "log", "-1", "--pretty=%H%n%s%n%ci"]),
}

report = {
    "generated_at": datetime.now(timezone.utc).isoformat(),
    "git": git,
    "inventory": {
        "python_files": len(python_files),
        "frontend_files": len(frontend_files),
        "modules": len(nodes),
        "routes": len(routes),
        "frontend_api_calls": len(frontend_calls),
        "syntax_errors": len(syntax_errors),
        "orphans": len(orphans),
    },
    "syntax_errors": syntax_errors,
    "nodes": nodes,
    "edges": {
        source: sorted(targets)
        for source, targets in edges.items()
    },
    "external_imports": {
        source: sorted(values)
        for source, values in external.items()
    },
    "orphans": orphans,
    "duplicate_classes": duplicate_classes,
    "routes": routes,
    "frontend_api_calls": frontend_calls,
    "frontend_calls_without_backend_route": missing_calls,
    "family_modules": family_modules,
    "central_modules": central[:100],
}

OUT.mkdir(parents=True, exist_ok=False)
(OUT / "dependency-report.json").write_text(
    json.dumps(report, ensure_ascii=False, indent=2),
    encoding="utf-8",
)

dot = [
    "digraph GeoCooling {",
    '  graph [rankdir="LR"];',
    '  node [shape="box", style="rounded"];',
]

focus = {
    module
    for module, node in nodes.items()
    if node["families"]
}

for module in sorted(focus):
    dot.append(f'  "{module}";')

for source, targets in edges.items():
    if source not in focus:
        continue
    for target in sorted(targets):
        if target in focus:
            dot.append(f'  "{source}" -> "{target}";')

dot.append("}")
(OUT / "dependency-graph.dot").write_text("\n".join(dot), encoding="utf-8")

def table(headers, rows):
    if not rows:
        return "_Aucune donnée._"
    lines = [
        "| " + " | ".join(headers) + " |",
        "| " + " | ".join("---" for _ in headers) + " |",
    ]
    for row in rows:
        lines.append(
            "| "
            + " | ".join(str(value).replace("|", "\\|") for value in row)
            + " |"
        )
    return "\n".join(lines)

markdown = f"""# GeoCooling RC1.1 — Dependency Analyzer

**Généré le :** {report["generated_at"]}  
**Branche :** `{git["branch"]["stdout"] or "inconnue"}`  
**Mode :** lecture seule

## Résumé

| Élément | Résultat |
|---|---:|
| Fichiers Python métier | {len(python_files)} |
| Fichiers frontend métier | {len(frontend_files)} |
| Modules Python | {len(nodes)} |
| Routes FastAPI | {len(routes)} |
| Appels API frontend | {len(frontend_calls)} |
| Erreurs de syntaxe | {len(syntax_errors)} |
| Modules sans import entrant | {len(orphans)} |
| Appels frontend sans route évidente | {len(missing_calls)} |

## État Git

```text
{git["status"]["stdout"] or "Arbre propre"}
```

## Modules centraux

{table(
    ["Module", "Familles", "Importé par", "Importe", "Fichier"],
    [
        [
            item["module"],
            ", ".join(item["families"]),
            len(item["imported_by"]),
            len(item["imports"]),
            item["file"],
        ]
        for item in central[:40]
    ],
)}
"""

for family in sorted(FAMILIES):
    items = family_modules.get(family, [])
    markdown += f"""
## Famille : {family}

{table(
    ["Module", "Importé par", "Importe", "Fichier"],
    [
        [
            item["module"],
            len(item["imported_by"]),
            len(item["imports"]),
            item["file"],
        ]
        for item in sorted(
            items,
            key=lambda value: (
                len(value["imported_by"]),
                len(value["imports"]),
            ),
            reverse=True,
        )
    ],
)}
"""

markdown += f"""
## Modules potentiellement orphelins

{table(
    ["Module", "Familles", "Fichier"],
    [
        [
            item["module"],
            ", ".join(item["families"]),
            item["file"],
        ]
        for item in orphans[:150]
    ],
)}

## Appels frontend sans route backend évidente

{table(
    ["Chemin", "Fichier", "Ligne"],
    [
        [item["path"], item["file"], item["line"]]
        for item in missing_calls
    ],
)}

## Classes portant le même nom

{table(
    ["Classe", "Occurrences"],
    [
        [
            name,
            "<br>".join(
                f"`{item['module']}` — `{item['file']}`"
                for item in values
            ),
        ]
        for name, values in sorted(duplicate_classes.items())
    ],
)}

## Fichiers générés

- `DEPENDENCY_REPORT.md`
- `dependency-report.json`
- `dependency-graph.dot`
"""

(OUT / "DEPENDENCY_REPORT.md").write_text(markdown, encoding="utf-8")

latest = ROOT / "audits" / "dependency-latest"
if latest.is_symlink() or latest.exists():
    latest.unlink()
latest.symlink_to(OUT.name, target_is_directory=True)

print("============================================================")
print(" RC1.1 DEPENDENCY ANALYZER TERMINÉ")
print("============================================================")
print("Python métier              :", len(python_files))
print("Frontend métier            :", len(frontend_files))
print("Modules                    :", len(nodes))
print("Routes                     :", len(routes))
print("Appels frontend            :", len(frontend_calls))
print("Erreurs syntaxe            :", len(syntax_errors))
print("Orphelins potentiels       :", len(orphans))
print("Appels frontend sans route :", len(missing_calls))
print("Rapport :", OUT / "DEPENDENCY_REPORT.md")
