from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query

from app.devices.manager import DeviceManager

router = APIRouter(prefix="/devices", tags=["Devices"])
_service: DeviceManager | None = None


def configure_devices_router(service: DeviceManager) -> None:
    global _service
    _service = service


def service() -> DeviceManager:
    if _service is None:
        raise RuntimeError("Device router non configuré")
    return _service


@router.get("")
def list_devices() -> dict[str, Any]:
    return {"devices": service().list_devices(), "diagnostics": service().status()}


@router.get("/diagnostics")
def device_diagnostics() -> dict[str, Any]:
    return service().status()


@router.post("/refresh")
def refresh_devices() -> dict[str, Any]:
    return service().refresh()


@router.get("/events")
def device_events(
    device_id: str | None = None,
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    return {"events": service().events(device_id=device_id, limit=limit)}


@router.get("/{device_id}")
def get_device(device_id: str) -> dict[str, Any]:
    device = service().get_device(device_id)
    if device is None:
        raise HTTPException(status_code=404, detail="Équipement inconnu")
    return device
