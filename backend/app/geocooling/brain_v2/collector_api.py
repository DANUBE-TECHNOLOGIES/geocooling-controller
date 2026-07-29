from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query

from app.geocooling.brain_v2.learning.automatic_collector import (
    AutomaticObservationCollector,
)


router = APIRouter(
    prefix="/collector",
    tags=["geocooling-brain-v2-collector"],
)

collector = AutomaticObservationCollector()


@router.on_event("startup")
def start_automatic_collector() -> None:
    collector.start()


@router.on_event("shutdown")
def stop_automatic_collector() -> None:
    collector.stop()


@router.get("/status")
def get_collector_status() -> dict:
    return collector.status()


@router.post("/collect")
def collect_observation(
    force: bool = Query(
        default=False
    ),
) -> dict:
    try:
        return collector.collect_once(
            force=force
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Automatic collection failed: {exc}",
        ) from exc


@router.post("/train")
def train_collected_observations() -> dict:
    try:
        return collector.train_once()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Automatic training failed: {exc}",
        ) from exc


@router.post("/cycle")
def execute_collection_cycle(
    force_collection: bool = Query(
        default=False
    ),
) -> dict:
    try:
        return collector.cycle_once(
            force_collection=force_collection
        )

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Automatic cycle failed: {exc}",
        ) from exc
