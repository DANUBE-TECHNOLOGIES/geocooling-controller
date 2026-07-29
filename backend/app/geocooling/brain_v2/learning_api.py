from __future__ import annotations

from fastapi import APIRouter, HTTPException

from app.geocooling.brain_v2.learning.thermal_learning_engine import (
    ThermalLearningEngine,
)


router = APIRouter(
    prefix="/learning",
    tags=["geocooling-brain-v2-learning"],
)

engine = ThermalLearningEngine()


@router.get("/status")
def get_learning_status() -> dict:
    try:
        return engine.status()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Thermal learning status failed: {exc}",
        ) from exc


@router.get("/model")
def get_learning_model() -> dict:
    try:
        return engine.read_model()
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Thermal learning model failed: {exc}",
        ) from exc


@router.post("/train")
def train_learning_model() -> dict:
    try:
        model = engine.train()

        return {
            "result": "TRAINING_COMPLETED",
            "model": model.to_dict(),
            "safety": {
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
            },
        }

    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=f"Thermal learning training failed: {exc}",
        ) from exc
