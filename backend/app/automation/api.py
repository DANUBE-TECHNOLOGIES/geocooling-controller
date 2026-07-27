from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.automation.models import AutomationAction, AutomationMode
from app.automation.service import AutomationService

router = APIRouter(prefix="/automation", tags=["automation"])
_service: AutomationService | None = None


class ExecuteRequest(BaseModel):
    subsystem: str = Field(default="geocooling", min_length=3, max_length=80)
    action: AutomationAction
    mode: AutomationMode = AutomationMode.SIMULATION
    requested_by: str = Field(default="api", min_length=2, max_length=80)
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    reason: str | None = Field(default=None, max_length=500)
    metadata: dict[str, Any] = Field(default_factory=dict)


class SimulateRequest(BaseModel):
    action: AutomationAction
    duration_minutes: int | None = Field(default=None, ge=1, le=1440)
    reason: str | None = Field(default=None, max_length=500)


def configure_automation_router(service: AutomationService) -> None:
    global _service
    _service = service


def service() -> AutomationService:
    if _service is None:
        raise HTTPException(status_code=503, detail="Automation Engine non configuré")
    return _service


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    return service().diagnostics()


@router.get("/executions")
def executions(
    limit: int = Query(100, ge=1, le=500),
    state: str | None = None,
) -> dict[str, Any]:
    items = service().list(limit=limit, state=state)
    return {"items": items, "count": len(items)}


@router.get("/executions/{execution_id}")
def execution(execution_id: str) -> dict[str, Any]:
    item = service().get(execution_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Exécution inconnue")
    return item


@router.post("/execute", status_code=202)
def execute(request: ExecuteRequest) -> dict[str, Any]:
    item = service().create(
        subsystem=request.subsystem,
        action=request.action,
        mode=request.mode,
        requested_by=request.requested_by,
        duration_minutes=request.duration_minutes,
        reason=request.reason,
        metadata=request.metadata,
    )
    return item.to_dict()


@router.post("/simulate", status_code=202)
def simulate(request: SimulateRequest) -> dict[str, Any]:
    item = service().create(
        subsystem="geocooling",
        action=request.action,
        mode=AutomationMode.SIMULATION,
        requested_by="simulation_api",
        duration_minutes=request.duration_minutes,
        reason=request.reason,
    )
    return item.to_dict()


@router.post("/executions/{execution_id}/cancel")
def cancel(execution_id: str) -> dict[str, Any]:
    item = service().cancel(execution_id)
    if item is None:
        raise HTTPException(status_code=404, detail="Exécution inconnue")
    return item
