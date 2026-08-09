"""
Read-only RC1 pipeline observability.

This module does not start services, write to hardware, publish MQTT messages,
or mutate the database. It reports whether the canonical RC1 modules and
symbols are importable.
"""

from __future__ import annotations

import importlib
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from typing import Any

from app.geocooling.rc1_architecture import CANONICAL_PIPELINE


@dataclass(frozen=True, slots=True)
class PipelineCheck:
    role: str
    module: str
    symbol: str | None
    module_available: bool
    symbol_available: bool | None
    healthy: bool
    detail: str


def _check_component(role: str, module: str, symbol: str | None) -> PipelineCheck:
    try:
        imported = importlib.import_module(module)
    except Exception as exc:
        return PipelineCheck(
            role=role,
            module=module,
            symbol=symbol,
            module_available=False,
            symbol_available=None,
            healthy=False,
            detail=f"{type(exc).__name__}: {exc}",
        )

    if symbol is None:
        return PipelineCheck(
            role=role,
            module=module,
            symbol=None,
            module_available=True,
            symbol_available=None,
            healthy=True,
            detail="module importable",
        )

    available = hasattr(imported, symbol)

    return PipelineCheck(
        role=role,
        module=module,
        symbol=symbol,
        module_available=True,
        symbol_available=available,
        healthy=available,
        detail=(
            "symbol available"
            if available
            else f"symbol {symbol!r} not found"
        ),
    )


def pipeline_status() -> dict[str, Any]:
    checks = [
        _check_component(
            role=component.role,
            module=component.module,
            symbol=component.symbol,
        )
        for component in CANONICAL_PIPELINE
    ]

    failed = [
        check.role
        for check in checks
        if not check.healthy
    ]

    return {
        "schema": "geocooling.rc1.pipeline-status.v1",
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": "read_only",
        "ready": not failed,
        "failed_roles": failed,
        "checks": [asdict(check) for check in checks],
        "safety": {
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
            "service_start": False,
        },
    }
