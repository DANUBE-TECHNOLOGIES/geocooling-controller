"""
Read-only API for the frozen RC1 architecture and canonical pipeline.
"""

from __future__ import annotations

from fastapi import APIRouter

from app.geocooling.rc1_architecture import architecture_status
from app.geocooling.rc1_pipeline import pipeline_status

router = APIRouter(
    prefix="/geocooling/rc1",
    tags=["GeoCooling RC1"],
)


@router.get("/architecture")
def get_rc1_architecture() -> dict[str, object]:
    return architecture_status()


@router.get("/pipeline")
def get_rc1_pipeline() -> dict[str, object]:
    return pipeline_status()


@router.get("/readiness")
def get_rc1_readiness() -> dict[str, object]:
    architecture = architecture_status()
    pipeline = pipeline_status()

    return {
        "schema": "geocooling.rc1.readiness.v1",
        "ready": bool(architecture["ready"] and pipeline["ready"]),
        "architecture_ready": architecture["ready"],
        "pipeline_ready": pipeline["ready"],
        "missing_required": architecture["missing_required"],
        "failed_roles": pipeline["failed_roles"],
        "safety": pipeline["safety"],
    }
