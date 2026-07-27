from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from app.geocooling.controller import GeoCoolingController
from app.geocooling.health_manager import GeoCoolingHealthManager
from app.geocooling.commissioning_manager import GeoCoolingCommissioningManager
from app.geocooling.commissioning_test_manager import GeoCoolingCommissioningTestManager

router = APIRouter(prefix="/geocooling", tags=["GeoCooling"])
controller = GeoCoolingController()
health_manager = GeoCoolingHealthManager(controller)
commissioning_manager = GeoCoolingCommissioningManager(controller, health_manager)
commissioning_test_manager = GeoCoolingCommissioningTestManager(controller)


@router.get("/status")
def get_status() -> dict:
    return controller.status()


@router.get("/device")
def get_device_status() -> dict:
    return controller.device_manager.status()


@router.post("/start")
def start_geocooling() -> JSONResponse:
    result = controller.request_start()
    return JSONResponse(status_code=202 if result["accepted"] else 409, content=result)


@router.post("/stop")
def stop_geocooling() -> JSONResponse:
    result = controller.request_stop()
    return JSONResponse(status_code=202 if result["accepted"] else 409, content=result)


@router.post("/emergency-stop")
def emergency_stop() -> JSONResponse:
    return JSONResponse(status_code=200, content=controller.emergency_stop())


@router.post("/reset")
def reset_controller() -> JSONResponse:
    result = controller.reset()
    return JSONResponse(status_code=200 if result["accepted"] else 409, content=result)


@router.get("/history")
def get_history(limit: int = Query(default=50, ge=1, le=500)) -> dict:
    return {"count": limit, "items": controller.history(limit)}


@router.get("/diagnostics")
def get_diagnostics() -> dict:
    return controller.diagnostics()


@router.get("/safety")
def get_safety() -> dict:
    return controller.status()["safety"]


@router.put("/thermal-snapshot")
def put_thermal_snapshot(payload: dict[str, Any] = Body(...)) -> dict:
    try:
        return controller.ingest_thermal_snapshot(payload)
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/thermal")
def get_thermal() -> dict:
    return controller.thermal_status()


@router.get("/thermal/history")
def get_thermal_history(limit: int = Query(default=200, ge=1, le=5000)) -> dict:
    items = controller.thermal_history(limit)
    return {"count": len(items), "items": items}


@router.get("/autopilot")
def get_autopilot() -> dict:
    return controller.autopilot_status()


@router.get("/brain")
def get_brain() -> dict:
    return controller.brain_status()


@router.get("/prediction")
def get_prediction() -> dict:
    return controller.prediction_status()


@router.get("/home-assistant")
def get_home_assistant_status() -> dict:
    return controller.home_assistant_status()


# PATCH-001E-MANUAL-COMMAND-API
def _manual_payload_value(
    payload: dict | None,
    key: str,
    default: object,
) -> object:
    if payload is None:
        return default

    if not isinstance(payload, dict):
        raise HTTPException(
            status_code=422,
            detail="Le corps de la requête doit être un objet JSON.",
        )

    return payload.get(key, default)


def _manual_requested_by(
    payload: dict | None,
) -> str:
    value = _manual_payload_value(
        payload,
        "requested_by",
        "home-assistant",
    )

    if not isinstance(value, str):
        raise HTTPException(
            status_code=422,
            detail="requested_by doit être une chaîne.",
        )

    value = value.strip()

    return value or "home-assistant"


def _manual_reason(
    payload: dict | None,
    default: str,
) -> str:
    value = _manual_payload_value(
        payload,
        "reason",
        default,
    )

    if not isinstance(value, str):
        raise HTTPException(
            status_code=422,
            detail="reason doit être une chaîne.",
        )

    return value.strip() or default


def _manual_duration(
    payload: dict | None,
) -> int:
    value = _manual_payload_value(
        payload,
        "duration_seconds",
        controller.command_manager.DEFAULT_DURATION_SECONDS,
    )

    if isinstance(value, bool):
        raise HTTPException(
            status_code=422,
            detail="duration_seconds doit être un entier.",
        )

    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail="duration_seconds doit être un entier.",
        ) from exc


def _manual_metadata(
    payload: dict | None,
) -> dict:
    value = _manual_payload_value(
        payload,
        "metadata",
        {},
    )

    if value is None:
        return {}

    if not isinstance(value, dict):
        raise HTTPException(
            status_code=422,
            detail="metadata doit être un objet JSON.",
        )

    return dict(value)


def _persist_active_manual_command() -> None:
    command = controller.command_manager.active_command_object()

    if command is not None:
        controller.brain_memory.save_manual_command(command)


def _record_manual_event(
    *,
    event_type: str,
    reason: str,
    details: dict,
    level: str = "INFO",
) -> None:
    controller.brain_memory.record_event(
        level=level,
        event_type=event_type,
        reason=reason,
        source="manual-api",
        details=details,
    )


def _create_manual_command(
    *,
    command_type: str,
    payload: dict | None,
) -> dict:
    requested_by = _manual_requested_by(payload)
    duration_seconds = _manual_duration(payload)
    reason = _manual_reason(
        payload,
        (
            "Demande de démarrage manuel sécurisé"
            if command_type == "START"
            else "Demande d'arrêt manuel sécurisé"
        ),
    )
    metadata = _manual_metadata(payload)

    metadata.setdefault("source", "rest-api")
    metadata.setdefault("api_route", f"/geocooling/manual/{command_type.lower()}")

    try:
        result = controller.command_manager.request(
            command_type=command_type,
            requested_by=requested_by,
            duration_seconds=duration_seconds,
            reason=reason,
            metadata=metadata,
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(
            status_code=422,
            detail=str(exc),
        ) from exc

    if not result.get("accepted"):
        raise HTTPException(
            status_code=409,
            detail={
                "message": result.get(
                    "reason",
                    "Commande manuelle refusée.",
                ),
                "active_command": result.get("active_command"),
            },
        )

    command = controller.command_manager.active_command_object()

    if command is None:
        raise HTTPException(
            status_code=500,
            detail="La commande créée est introuvable.",
        )

    try:
        controller.brain_memory.save_manual_command(command)

        _record_manual_event(
            event_type=(
                "geocooling.manual.start_requested"
                if command_type == "START"
                else "geocooling.manual.stop_requested"
            ),
            reason=reason,
            details={
                "command_id": command.id,
                "command": command.command.value,
                "status": command.status.value,
                "requested_by": command.requested_by,
                "duration_seconds": command.duration_seconds,
                "metadata": dict(command.metadata),
            },
        )
    except Exception as exc:
        controller.command_manager.cancel(
            requested_by="system",
            reason="Échec de persistance PostgreSQL",
        )

        raise HTTPException(
            status_code=500,
            detail=(
                "La commande n'a pas été conservée car son "
                "historisation PostgreSQL a échoué."
            ),
        ) from exc

    execution = controller.execute_pending_manual_command()

    execution["manual_status"] = (
        controller.command_manager.status()
    )

    return execution


@router.post("/manual/start")
def manual_start(
    payload: dict | None = Body(default=None),
) -> dict:
    """
    Enregistre une demande de démarrage manuel sécurisé.

    Cette route ne pilote pas directement les équipements.
    """

    return _create_manual_command(
        command_type="START",
        payload=payload,
    )


@router.post("/manual/stop")
def manual_stop(
    payload: dict | None = Body(default=None),
) -> dict:
    """
    Enregistre une demande d'arrêt manuel sécurisé.

    Cette route ne pilote pas directement les équipements.
    """

    return _create_manual_command(
        command_type="STOP",
        payload=payload,
    )


@router.post("/manual/cancel")
def manual_cancel(
    payload: dict | None = Body(default=None),
) -> JSONResponse:
    """
    Annule la commande manuelle active.

    Lorsqu'un START est déjà en cours, le contrôleur demande d'abord
    l'arrêt sécurisé de l'installation. La commande n'est pas retirée
    prématurément si l'arrêt est temporairement différé.
    """

    requested_by = _manual_requested_by(payload)
    reason = _manual_reason(
        payload,
        "Annulation de la commande manuelle",
    )

    try:
        result = controller.cancel_manual_command(
            requested_by=requested_by,
            reason=reason,
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail=(
                "Échec de l'annulation sécurisée de la commande "
                "manuelle."
            ),
        ) from exc

    status_code = int(
        result.pop(
            "status_code",
            200 if result.get("accepted") else 409,
        )
    )

    result["manual_status"] = (
        controller.command_manager.status()
    )

    return JSONResponse(
        status_code=status_code,
        content=result,
    )


@router.get("/manual/status")
def manual_status() -> dict:
    """
    Retourne la commande active et l'état du gestionnaire.
    """

    expired_command = controller.command_manager.cleanup_expired()

    if expired_command is not None:
        try:
            recent_objects = controller.command_manager.history(limit=1)

            _record_manual_event(
                event_type="geocooling.manual.command_expired",
                reason="Durée maximale de la commande dépassée",
                details={
                    "command": expired_command,
                    "history_head": (
                        recent_objects[0]
                        if recent_objects
                        else None
                    ),
                },
                level="WARNING",
            )
        except Exception:
            pass

    status = controller.command_manager.status()

    return {
        "active": status["active"],
        "active_command": status["active_command"],
        "history_count": status["history_count"],
        "duration_limits": status["duration_limits"],
        "controller": {
            "mode": controller.mode.value,
            "state": controller.state.value,
        },
    }


@router.get("/manual/history")
def manual_history(
    limit: int = Query(default=50, ge=1, le=500),
) -> dict:
    """
    Retourne l'historique mémoire et l'historique PostgreSQL.
    """

    try:
        persisted = controller.brain_memory.recent_manual_commands(
            limit=limit
        )
    except Exception as exc:
        raise HTTPException(
            status_code=500,
            detail="Lecture de l'historique PostgreSQL impossible.",
        ) from exc

    return {
        "limit": limit,
        "active_command": (
            controller.command_manager.active_command()
        ),
        "memory_history": controller.command_manager.history(
            limit=limit
        ),
        "persisted_history": persisted,
        "persisted_count": len(persisted),
    }

@router.get("/health")
def get_geocooling_health() -> dict:
    """Retourne le diagnostic GeoCooling consolidé en lecture seule."""

    return health_manager.status()

@router.get("/commissioning")
def get_geocooling_commissioning() -> dict:
    """Retourne la checklist GeoCooling de mise en service."""

    return commissioning_manager.status()

@router.get("/commissioning/tests")
def get_geocooling_commissioning_tests() -> dict:
    """Retourne l'état des tests temporisés de mise en service."""

    return commissioning_test_manager.status()


@router.post("/commissioning/test/valve")
def test_geocooling_valve(
    payload: dict = Body(default={}),
) -> dict:
    """Lance un test temporisé de l'électrovanne."""

    try:
        return commissioning_test_manager.start_test(
            target="valve",
            duration_seconds=payload.get(
                "duration_seconds"
            ),
            confirmation=payload.get(
                "confirmation"
            ),
            requested_by=str(
                payload.get(
                    "requested_by",
                    "api",
                )
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post("/commissioning/test/pump")
def test_geocooling_pump(
    payload: dict = Body(default={}),
) -> dict:
    """Lance un test hydraulique temporisé du circulateur."""

    try:
        return commissioning_test_manager.start_test(
            target="pump",
            duration_seconds=payload.get(
                "duration_seconds"
            ),
            confirmation=payload.get(
                "confirmation"
            ),
            requested_by=str(
                payload.get(
                    "requested_by",
                    "api",
                )
            ),
        )

    except ValueError as exc:
        raise HTTPException(
            status_code=400,
            detail=str(exc),
        ) from exc

    except RuntimeError as exc:
        raise HTTPException(
            status_code=409,
            detail=str(exc),
        ) from exc


@router.post("/commissioning/test/cancel")
def cancel_geocooling_commissioning_test() -> dict:
    """Annule le test actif et impose l'arrêt des sorties."""

    return commissioning_test_manager.cancel_test()

