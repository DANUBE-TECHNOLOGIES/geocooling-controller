"""
Utilitaires internes pour les patchs architecturaux GeoCooling.

PATCH C012.F — Patch Foundation

Ce module ne contient aucune logique métier du contrôleur.

Il fournit uniquement :

- introspection sûre des objets Python ;
- analyse des signatures ;
- découverte des méthodes publiques ;
- détection des méthodes appelables sans argument obligatoire ;
- analyse AST des classes, méthodes et routes FastAPI ;
- calcul d'une position d'insertion avant les décorateurs ;
- validation syntaxique et structurelle ;
- helpers d'édition de fichiers avec écriture atomique.

Le module est volontairement indépendant de FastAPI, Docker,
SQLAlchemy, MQTT et des composants GeoCooling.
"""

from __future__ import annotations

import ast
import hashlib
import inspect
import json
import os
import tempfile
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, Mapping, Sequence


PATCH_FOUNDATION_VERSION = "C012.F"


class PatchUtilityError(RuntimeError):
    """Erreur contrôlée produite par les utilitaires de patch."""


@dataclass(frozen=True)
class ParameterDescriptor:
    """Description sérialisable d'un paramètre de méthode."""

    name: str
    kind: str
    required: bool
    has_default: bool
    default_repr: str | None
    annotation_repr: str | None


@dataclass(frozen=True)
class MethodDescriptor:
    """Description sérialisable d'une méthode inspectée."""

    name: str
    public: bool
    callable: bool
    signature_available: bool
    callable_without_arguments: bool
    required_parameter_count: int
    parameter_count: int
    is_coroutine: bool
    parameters: tuple[ParameterDescriptor, ...]
    error: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class RouteDescriptor:
    """Description d'une route détectée dans un module Python."""

    function_name: str
    function_line: int
    decorator_start_line: int
    decorator_end_line: int
    decorator_expressions: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


@dataclass(frozen=True)
class ClassDescriptor:
    """Description AST minimale d'une classe Python."""

    name: str
    line: int
    end_line: int
    methods: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def safe_repr(value: Any, max_length: int = 300) -> str:
    """
    Retourne une représentation bornée et non bloquante.
    """

    try:
        result = repr(value)
    except Exception as exc:
        result = f"<repr failed: {type(exc).__name__}: {exc}>"

    if len(result) > max_length:
        result = result[: max_length - 3] + "..."

    return result


def json_safe(value: Any) -> Any:
    """
    Convertit une valeur vers une forme sérialisable JSON.

    Cette fonction est tolérante :
    une valeur inconnue devient une chaîne plutôt que de lever
    une exception.
    """

    if value is None:
        return None

    if isinstance(value, (str, int, float, bool)):
        return value

    enum_value = getattr(value, "value", None)

    if isinstance(enum_value, (str, int, float, bool)):
        return enum_value

    if isinstance(value, Mapping):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(value, (list, tuple, set, frozenset)):
        return [json_safe(item) for item in value]

    if isinstance(value, Path):
        return str(value)

    if hasattr(value, "isoformat"):
        try:
            return value.isoformat()
        except Exception:
            pass

    return safe_repr(value)


def file_sha256(path: str | Path) -> str:
    """Calcule le SHA-256 d'un fichier."""

    file_path = Path(path)
    digest = hashlib.sha256()

    with file_path.open("rb") as handle:
        while True:
            chunk = handle.read(1024 * 1024)

            if not chunk:
                break

            digest.update(chunk)

    return digest.hexdigest()


def read_text(path: str | Path) -> str:
    """Lit un fichier UTF-8."""

    return Path(path).read_text(encoding="utf-8")


def validate_python_source(
    source: str,
    *,
    filename: str = "<memory>",
) -> ast.Module:
    """
    Parse une source Python et retourne son AST.

    Une PatchUtilityError claire est levée en cas d'erreur.
    """

    try:
        return ast.parse(source, filename=filename)
    except SyntaxError as exc:
        line = exc.lineno or 0
        offset = exc.offset or 0
        message = exc.msg or "syntaxe Python invalide"

        raise PatchUtilityError(
            f"{filename}:{line}:{offset}: {message}"
        ) from exc


def validate_python_file(path: str | Path) -> ast.Module:
    """Valide syntaxiquement un fichier Python."""

    file_path = Path(path)

    return validate_python_source(
        read_text(file_path),
        filename=str(file_path),
    )


def atomic_write_text(
    path: str | Path,
    content: str,
    *,
    validate_python: bool = False,
) -> None:
    """
    Écrit un fichier de manière atomique.

    Le contenu peut être validé comme source Python avant écriture.
    """

    file_path = Path(path)
    file_path.parent.mkdir(parents=True, exist_ok=True)

    if validate_python:
        validate_python_source(
            content,
            filename=str(file_path),
        )

    current_mode: int | None = None

    if file_path.exists():
        current_mode = file_path.stat().st_mode

    descriptor, temporary_name = tempfile.mkstemp(
        prefix=f".{file_path.name}.",
        suffix=".tmp",
        dir=str(file_path.parent),
        text=True,
    )

    temporary_path = Path(temporary_name)

    try:
        with os.fdopen(
            descriptor,
            "w",
            encoding="utf-8",
            newline="",
        ) as handle:
            handle.write(content)
            handle.flush()
            os.fsync(handle.fileno())

        if current_mode is not None:
            os.chmod(temporary_path, current_mode)

        os.replace(temporary_path, file_path)

    except Exception:
        temporary_path.unlink(missing_ok=True)
        raise


def inspect_parameter(
    parameter: inspect.Parameter,
) -> ParameterDescriptor:
    """Transforme un paramètre inspecté en structure sérialisable."""

    has_default = (
        parameter.default is not inspect.Parameter.empty
    )

    annotation_available = (
        parameter.annotation is not inspect.Parameter.empty
    )

    required = (
        not has_default
        and parameter.kind
        not in (
            inspect.Parameter.VAR_POSITIONAL,
            inspect.Parameter.VAR_KEYWORD,
        )
    )

    return ParameterDescriptor(
        name=parameter.name,
        kind=parameter.kind.name,
        required=required,
        has_default=has_default,
        default_repr=(
            safe_repr(parameter.default)
            if has_default
            else None
        ),
        annotation_repr=(
            safe_repr(parameter.annotation)
            if annotation_available
            else None
        ),
    )


def inspect_method(
    component: Any,
    method_name: str,
) -> MethodDescriptor:
    """
    Inspecte une méthode sans l'exécuter.

    Aucun appel métier n'est effectué.
    """

    public = not method_name.startswith("_")

    try:
        candidate = getattr(component, method_name)
    except Exception as exc:
        return MethodDescriptor(
            name=method_name,
            public=public,
            callable=False,
            signature_available=False,
            callable_without_arguments=False,
            required_parameter_count=0,
            parameter_count=0,
            is_coroutine=False,
            parameters=(),
            error=(
                f"{type(exc).__name__}: {exc}"
            ),
        )

    if not callable(candidate):
        return MethodDescriptor(
            name=method_name,
            public=public,
            callable=False,
            signature_available=False,
            callable_without_arguments=False,
            required_parameter_count=0,
            parameter_count=0,
            is_coroutine=False,
            parameters=(),
            error=None,
        )

    try:
        signature = inspect.signature(candidate)
    except Exception as exc:
        return MethodDescriptor(
            name=method_name,
            public=public,
            callable=True,
            signature_available=False,
            callable_without_arguments=False,
            required_parameter_count=0,
            parameter_count=0,
            is_coroutine=inspect.iscoroutinefunction(
                candidate
            ),
            parameters=(),
            error=(
                f"{type(exc).__name__}: {exc}"
            ),
        )

    parameters = tuple(
        inspect_parameter(parameter)
        for parameter in signature.parameters.values()
    )

    required_count = sum(
        1
        for parameter in parameters
        if parameter.required
    )

    return MethodDescriptor(
        name=method_name,
        public=public,
        callable=True,
        signature_available=True,
        callable_without_arguments=required_count == 0,
        required_parameter_count=required_count,
        parameter_count=len(parameters),
        is_coroutine=inspect.iscoroutinefunction(candidate),
        parameters=parameters,
        error=None,
    )


def discover_methods(
    component: Any,
    *,
    include_private: bool = False,
) -> list[MethodDescriptor]:
    """
    Découvre les méthodes d'un objet sans les exécuter.
    """

    try:
        names = sorted(set(dir(component)))
    except Exception as exc:
        raise PatchUtilityError(
            "Impossible d'énumérer le composant : "
            f"{type(exc).__name__}: {exc}"
        ) from exc

    descriptors: list[MethodDescriptor] = []

    for name in names:
        if not include_private and name.startswith("_"):
            continue

        descriptor = inspect_method(component, name)

        if descriptor.callable:
            descriptors.append(descriptor)

    return descriptors


def methods_callable_without_arguments(
    component: Any,
    *,
    include_private: bool = False,
    include_coroutines: bool = False,
    preferred_names: Sequence[str] = (),
) -> list[MethodDescriptor]:
    """
    Retourne les méthodes appelables sans argument obligatoire.

    Le résultat est ordonné selon preferred_names puis par nom.

    La fonction n'appelle aucune méthode.
    """

    descriptors = discover_methods(
        component,
        include_private=include_private,
    )

    eligible = [
        descriptor
        for descriptor in descriptors
        if descriptor.signature_available
        and descriptor.callable_without_arguments
        and (
            include_coroutines
            or not descriptor.is_coroutine
        )
    ]

    preference = {
        name: index
        for index, name in enumerate(preferred_names)
    }

    fallback_rank = len(preference) + 1

    eligible.sort(
        key=lambda descriptor: (
            preference.get(
                descriptor.name,
                fallback_rank,
            ),
            descriptor.name,
        )
    )

    return eligible


def select_callable_method(
    component: Any,
    *,
    preferred_names: Sequence[str],
    include_private: bool = False,
    include_coroutines: bool = False,
) -> MethodDescriptor | None:
    """
    Sélectionne une méthode appelable sans argument obligatoire.

    La priorité est strictement donnée à preferred_names.

    Si aucune méthode préférée n'est trouvée, aucune méthode
    arbitraire n'est choisie.
    """

    methods = methods_callable_without_arguments(
        component,
        include_private=include_private,
        include_coroutines=include_coroutines,
        preferred_names=preferred_names,
    )

    preferred_set = set(preferred_names)

    for descriptor in methods:
        if descriptor.name in preferred_set:
            return descriptor

    return None


def component_report(
    component: Any,
    *,
    include_private: bool = False,
) -> dict[str, Any]:
    """
    Produit un rapport d'introspection sans exécution métier.
    """

    component_type = type(component)

    methods = discover_methods(
        component,
        include_private=include_private,
    )

    return {
        "type": component_type.__name__,
        "module": component_type.__module__,
        "method_count": len(methods),
        "methods": [
            descriptor.to_dict()
            for descriptor in methods
        ],
        "callable_without_arguments": [
            descriptor.name
            for descriptor in methods
            if descriptor.signature_available
            and descriptor.callable_without_arguments
            and not descriptor.is_coroutine
        ],
    }


def find_class(
    tree: ast.Module,
    class_name: str,
) -> ast.ClassDef | None:
    """Trouve une classe de premier niveau par son nom."""

    for node in tree.body:
        if (
            isinstance(node, ast.ClassDef)
            and node.name == class_name
        ):
            return node

    return None


def describe_class(
    source: str,
    class_name: str,
    *,
    filename: str = "<memory>",
) -> ClassDescriptor:
    """
    Décrit une classe présente dans une source Python.
    """

    tree = validate_python_source(
        source,
        filename=filename,
    )

    class_node = find_class(tree, class_name)

    if class_node is None:
        raise PatchUtilityError(
            f"Classe introuvable : {class_name}"
        )

    methods = tuple(
        node.name
        for node in class_node.body
        if isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        )
    )

    return ClassDescriptor(
        name=class_node.name,
        line=class_node.lineno,
        end_line=class_node.end_lineno or class_node.lineno,
        methods=methods,
    )


def find_method(
    class_node: ast.ClassDef,
    method_name: str,
) -> ast.FunctionDef | ast.AsyncFunctionDef | None:
    """Trouve une méthode directement déclarée dans une classe."""

    for node in class_node.body:
        if (
            isinstance(
                node,
                (ast.FunctionDef, ast.AsyncFunctionDef),
            )
            and node.name == method_name
        ):
            return node

    return None


def decorator_expression(
    decorator: ast.expr,
) -> str:
    """Retourne une représentation source d'un décorateur."""

    try:
        return ast.unparse(decorator)
    except Exception:
        return "<unparse unavailable>"


def is_route_decorator(
    decorator: ast.expr,
    *,
    router_names: Sequence[str] = (
        "router",
        "app",
    ),
    methods: Sequence[str] = (
        "get",
        "post",
        "put",
        "patch",
        "delete",
        "options",
        "head",
    ),
) -> bool:
    """
    Détermine si un décorateur ressemble à une route FastAPI.

    Aucune dépendance FastAPI n'est requise.
    """

    expression = decorator_expression(decorator)

    for router_name in router_names:
        for method in methods:
            if (
                f"{router_name}.{method}(" in expression
                or f".{method}(" in expression
            ):
                return True

    return False


def discover_routes(
    source: str,
    *,
    filename: str = "<memory>",
    router_names: Sequence[str] = (
        "router",
        "app",
    ),
) -> list[RouteDescriptor]:
    """
    Découvre les fonctions décorées comme routes.

    La position retournée commence au premier décorateur.
    """

    tree = validate_python_source(
        source,
        filename=filename,
    )

    routes: list[RouteDescriptor] = []

    for node in tree.body:
        if not isinstance(
            node,
            (ast.FunctionDef, ast.AsyncFunctionDef),
        ):
            continue

        route_decorators = [
            decorator
            for decorator in node.decorator_list
            if is_route_decorator(
                decorator,
                router_names=router_names,
            )
        ]

        if not route_decorators:
            continue

        all_decorators = (
            node.decorator_list
            if node.decorator_list
            else route_decorators
        )

        start_line = min(
            decorator.lineno
            for decorator in all_decorators
        )

        end_line = max(
            decorator.end_lineno or decorator.lineno
            for decorator in all_decorators
        )

        routes.append(
            RouteDescriptor(
                function_name=node.name,
                function_line=node.lineno,
                decorator_start_line=start_line,
                decorator_end_line=end_line,
                decorator_expressions=tuple(
                    decorator_expression(decorator)
                    for decorator in node.decorator_list
                ),
            )
        )

    routes.sort(
        key=lambda route: route.decorator_start_line
    )

    return routes


def first_route_insertion_line(
    source: str,
    *,
    filename: str = "<memory>",
    router_names: Sequence[str] = (
        "router",
        "app",
    ),
) -> int:
    """
    Retourne la ligne 1-indexée avant laquelle insérer du code.

    La ligne correspond au premier décorateur de la première route,
    jamais à la ligne du `def`.
    """

    routes = discover_routes(
        source,
        filename=filename,
        router_names=router_names,
    )

    if not routes:
        raise PatchUtilityError(
            "Aucune route FastAPI détectée."
        )

    return routes[0].decorator_start_line


def insert_before_line(
    source: str,
    line_number: int,
    block: str,
    *,
    filename: str = "<memory>",
    validate_result: bool = True,
) -> str:
    """
    Insère un bloc avant une ligne 1-indexée.
    """

    if line_number < 1:
        raise PatchUtilityError(
            f"Numéro de ligne invalide : {line_number}"
        )

    lines = source.splitlines(keepends=True)

    if line_number > len(lines) + 1:
        raise PatchUtilityError(
            "Numéro de ligne hors limites : "
            f"{line_number} > {len(lines) + 1}"
        )

    normalized_block = block

    if not normalized_block.startswith("\n"):
        normalized_block = "\n" + normalized_block

    if not normalized_block.endswith("\n"):
        normalized_block += "\n"

    index = line_number - 1
    lines.insert(index, normalized_block)

    result = "".join(lines)

    if validate_result:
        validate_python_source(
            result,
            filename=filename,
        )

    return result


def insert_before_first_route(
    source: str,
    block: str,
    *,
    filename: str = "<memory>",
    router_names: Sequence[str] = (
        "router",
        "app",
    ),
) -> str:
    """
    Insère un bloc avant le premier décorateur de route.
    """

    line_number = first_route_insertion_line(
        source,
        filename=filename,
        router_names=router_names,
    )

    return insert_before_line(
        source,
        line_number,
        block,
        filename=filename,
        validate_result=True,
    )


def assert_fragments(
    source: str,
    required: Iterable[str],
    *,
    filename: str = "<memory>",
) -> None:
    """Vérifie la présence de fragments textuels."""

    missing = [
        fragment
        for fragment in required
        if fragment not in source
    ]

    if missing:
        formatted = ", ".join(
            repr(fragment)
            for fragment in missing
        )

        raise PatchUtilityError(
            f"{filename}: fragments absents : {formatted}"
        )


def assert_fragment_count(
    source: str,
    fragment: str,
    expected: int,
    *,
    filename: str = "<memory>",
) -> None:
    """Vérifie le nombre d'occurrences d'un fragment."""

    actual = source.count(fragment)

    if actual != expected:
        raise PatchUtilityError(
            f"{filename}: {fragment!r} présent "
            f"{actual} fois au lieu de {expected}."
        )


def replace_once(
    source: str,
    old: str,
    new: str,
    *,
    filename: str = "<memory>",
) -> str:
    """
    Remplace exactement une occurrence.
    """

    count = source.count(old)

    if count != 1:
        raise PatchUtilityError(
            f"{filename}: remplacement ambigu pour "
            f"{old!r}, occurrences={count}."
        )

    return source.replace(old, new, 1)


def dump_report(
    report: Mapping[str, Any],
    *,
    indent: int = 2,
) -> str:
    """Sérialise un rapport en JSON lisible."""

    return json.dumps(
        json_safe(report),
        indent=indent,
        ensure_ascii=False,
        sort_keys=True,
    )


__all__ = [
    "PATCH_FOUNDATION_VERSION",
    "PatchUtilityError",
    "ParameterDescriptor",
    "MethodDescriptor",
    "RouteDescriptor",
    "ClassDescriptor",
    "safe_repr",
    "json_safe",
    "file_sha256",
    "read_text",
    "validate_python_source",
    "validate_python_file",
    "atomic_write_text",
    "inspect_parameter",
    "inspect_method",
    "discover_methods",
    "methods_callable_without_arguments",
    "select_callable_method",
    "component_report",
    "find_class",
    "describe_class",
    "find_method",
    "decorator_expression",
    "is_route_decorator",
    "discover_routes",
    "first_route_insertion_line",
    "insert_before_line",
    "insert_before_first_route",
    "assert_fragments",
    "assert_fragment_count",
    "replace_once",
    "dump_report",
]
