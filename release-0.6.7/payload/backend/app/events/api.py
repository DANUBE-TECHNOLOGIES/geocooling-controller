from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.events.bus import EventBus
from app.events.models import EventPriority

router = APIRouter(prefix="/events", tags=["events"])
_bus: EventBus | None = None


class PublishEventRequest(BaseModel):
    event_type: str = Field(min_length=3, max_length=160)
    source: str = Field(min_length=2, max_length=100)
    priority: EventPriority = EventPriority.INFO
    correlation_id: str | None = Field(default=None, max_length=160)
    payload: dict[str, Any] = Field(default_factory=dict)


def configure_events_router(bus: EventBus) -> None:
    global _bus
    _bus = bus


def get_bus() -> EventBus:
    if _bus is None:
        raise HTTPException(status_code=503, detail="Event Bus non configuré")
    return _bus


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    return get_bus().diagnostics()


@router.get("/recent")
def recent(
    limit: int = Query(50, ge=1, le=500),
    event_type: str | None = None,
    source: str | None = None,
    persisted: bool = True,
) -> dict[str, Any]:
    events = get_bus().recent(limit, event_type, source, persisted)
    return {"events": events, "count": len(events)}


@router.get("/types")
def types() -> dict[str, Any]:
    items = get_bus().event_types()
    return {"types": items, "count": len(items)}


@router.post("/publish", status_code=202)
def publish(request: PublishEventRequest) -> dict[str, Any]:
    event_id = get_bus().publish(
        request.event_type,
        request.source,
        request.payload,
        request.priority,
        request.correlation_id,
    )
    return {"accepted": True, "event_id": event_id}
