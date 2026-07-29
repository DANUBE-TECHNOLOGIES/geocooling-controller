from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.geocooling.brain_v2.decision.automatic_advisor import (
    AutomaticAdvisoryOrchestrator,
)


router = APIRouter(
    prefix="/advisor",
    tags=["geocooling-brain-v2-advisor"],
)

advisor = AutomaticAdvisoryOrchestrator()


@router.on_event("startup")
def start_automatic_advisor() -> None:
    advisor.start()


@router.on_event("shutdown")
def stop_automatic_advisor() -> None:
    advisor.stop()


@router.get("/status")
def get_advisor_status() -> dict:
    return advisor.status()


@router.post("/evaluate")
def force_advisory_evaluation() -> dict:
    try:
        return advisor.evaluate_once()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Automatic advisory evaluation failed: {exc}"
            ),
        ) from exc


@router.get("/home-assistant")
def get_home_assistant_snapshot() -> dict:
    try:
        return advisor.latest_snapshot()

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                f"Home Assistant advisory snapshot failed: {exc}"
            ),
        ) from exc
