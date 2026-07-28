from typing import Any

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse

from app.geocooling.controller import GeoCoolingController
from app.geocooling.health_manager import GeoCoolingHealthManager
from app.geocooling.commissioning_manager import GeoCoolingCommissioningManager
from app.geocooling.commissioning_test_manager import GeoCoolingCommissioningTestManager
from app.geocooling.flight_recorder import GeoCoolingFlightRecorder
from app.geocooling.event_timeline import GeoCoolingEventTimeline
from app.geocooling.watchdog_manager import GeoCoolingWatchdog
from app.geocooling.runtime_manager import GeoCoolingRuntime
from app.geocooling.state_cache import GeoCoolingStateCache
from app.geocooling.event_subscription_manager import EventSubscriptionManager
from app.geocooling.event_consumers import GeoCoolingEventConsumers
from app.geocooling.realtime_metrics import GeoCoolingRealtimeMetrics
from app.geocooling.controller_command_bridge import GeoCoolingControllerCommandBridge
from app.geocooling.brain_decision_publisher import GeoCoolingBrainDecisionPublisher
from app.geocooling.controller_safety_gate import GeoCoolingControllerSafetyGate
from app.geocooling.execution_supervisor import GeoCoolingExecutionSupervisor
from app.geocooling.execution_analyzer import GeoCoolingExecutionAnalyzer
from app.geocooling.thermal_performance_analyzer import GeoCoolingThermalPerformanceAnalyzer
from app.geocooling.brain_feedback import GeoCoolingBrainFeedback
from app.geocooling.operational_certification import OperationalCertificationEngine
from app.geocooling.sensor_mqtt_discovery import SensorMQTTDiscovery
from app.geocooling.sensor_validation import SensorValidationEngine
from app.geocooling.mqtt_preflight import MQTTPreflightCertification
from app.geocooling.hardware_manual_control import (
    ARM_CONFIRMATION,
    HardwareManualControl,
)
from app.geocooling.hardware_certification import HardwareCertificationEngine
from app.geocooling.digital_twin import GeoCoolingDigitalTwin
from app.geocooling.water_test_framework import GeoCoolingWaterTestFramework, WaterTestError
from app.geocooling.operations_dashboard import GeoCoolingOperationsDashboard
from app.geocooling.thermal_forecast import GeoCoolingForecastEngine
from app.geocooling.digital_twin_calibration import DigitalTwinCalibration
from app.geocooling.efficiency_index import GeoCoolingEfficiencyIndex
from app.geocooling.drift_detector import GeoCoolingDriftDetector
from app.geocooling.assisted_calibration import AssistedCalibrationEngine
from app.geocooling.integration_audit import GeoCoolingIntegrationAudit
from app.geocooling.runtime_profiler import GeoCoolingRuntimeProfiler
from app.geocooling.alarm_engine import GeoCoolingAlarmEngine
from app.geocooling.operations_suite import GeoCoolingOperationsSuite
from app.geocooling.industrial_hardening import GeoCoolingIndustrialHardening, TransactionStep
from app.geocooling.industrial_platform import GeoCoolingIndustrialPlatform
from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver

router = APIRouter(prefix="/geocooling", tags=["GeoCooling"])
controller = GeoCoolingController()
health_manager = GeoCoolingHealthManager(controller)
commissioning_manager = GeoCoolingCommissioningManager(controller, health_manager)
commissioning_test_manager = GeoCoolingCommissioningTestManager(controller)
hardware_manual_control = HardwareManualControl(controller)
operations_dashboard = GeoCoolingOperationsDashboard(controller, hardware_manual_control)

def _c0241_route_provider() -> list[str]:
    return [route.path for route in router.routes]

integration_audit = GeoCoolingIntegrationAudit(
    controller, hardware_manual_control, operations_dashboard,
    route_provider=_c0241_route_provider,
)
forecast_engine = GeoCoolingForecastEngine(controller)
state_cache = GeoCoolingStateCache(controller)
controller.attach_state_cache(state_cache)
flight_recorder = GeoCoolingFlightRecorder(controller, state_cache)
event_timeline = GeoCoolingEventTimeline(controller, flight_recorder, commissioning_test_manager)
watchdog = GeoCoolingWatchdog(controller, flight_recorder, state_cache)

# Registre d'exécution central GeoCooling — PATCH C007
runtime = GeoCoolingRuntime(
    controller=controller,
    health_manager=health_manager,
    commissioning_manager=commissioning_manager,
    commissioning_test_manager=commissioning_test_manager,
    state_cache=state_cache,
    flight_recorder=flight_recorder,
    event_timeline=event_timeline,
    watchdog=watchdog,
)

# PATCH C011B — Snapshot Builder Runtime
runtime.register(
    "snapshot_builder",
    controller.snapshot_builder,
)

# PATCH C012.0 — Event Bus Runtime Registration
runtime.register(
    "event_bus",
    controller.event_bus,
)


# PATCH C012.2 — State Cache Event Bus Attachment
setattr(
    state_cache,
    "_event_bus",
    controller.event_bus,
)




# PATCH C012.3R4 — Brain Event Bus Attachment
_c0123r4_brain = getattr(controller, "brain", None)
_c0123r4_event_bus = getattr(controller, "event_bus", None)

if (
    _c0123r4_brain is not None
    and _c0123r4_event_bus is not None
):
    setattr(
        _c0123r4_brain,
        "_event_bus",
        _c0123r4_event_bus,
    )

# PATCH C012.4R1 — Predictor Event Bus Attachment
_c0124r1_predictor = getattr(
    controller,
    "predictor",
    None,
)

_c0124r1_event_bus = getattr(
    controller,
    "event_bus",
    None,
)

if (
    _c0124r1_predictor is not None
    and _c0124r1_event_bus is not None
):
    setattr(
        _c0124r1_predictor,
        "_event_bus",
        _c0124r1_event_bus,
    )

# PATCH C013.0R2 — Subscription Manager Bootstrap
event_subscription_manager = EventSubscriptionManager(
    history_capacity=200,
)

_c0130r2_event_bus = getattr(
    controller,
    "event_bus",
    None,
)

if _c0130r2_event_bus is None:
    raise RuntimeError(
        "C013.0R2 : controller.event_bus est absent."
    )

setattr(
    _c0130r2_event_bus,
    "_subscription_manager",
    event_subscription_manager,
)

setattr(
    controller,
    "event_subscription_manager",
    event_subscription_manager,
)

# PATCH C013.1+C013.2R1 — Event Consumers Bootstrap
event_consumers = GeoCoolingEventConsumers(
    subscription_manager=event_subscription_manager,
    flight_recorder=flight_recorder,
    event_timeline=event_timeline,
)

setattr(
    controller,
    "event_consumers",
    event_consumers,
)

# PATCH C013.3R1 — Realtime Metrics Bootstrap
realtime_metrics = GeoCoolingRealtimeMetrics(
    subscription_manager=event_subscription_manager,
)

setattr(
    controller,
    "realtime_metrics",
    realtime_metrics,
)

# PATCH C014.0R1 — Controller Command Bridge Bootstrap
controller_command_bridge = (
    GeoCoolingControllerCommandBridge(
        controller=controller,
        subscription_manager=event_subscription_manager,
        event_bus=controller.event_bus,
        armed=False,
        cooldown_seconds=30.0,
        deduplication_seconds=10.0,
    )
)

setattr(
    controller,
    "controller_command_bridge",
    controller_command_bridge,
)

# PATCH C014.1+C014.2R2 — Publisher and Safety Gate Bootstrap
brain_decision_publisher = (
    GeoCoolingBrainDecisionPublisher(
        subscription_manager=event_subscription_manager,
        event_bus=controller.event_bus,
        deduplication_seconds=2.0,
    )
)

controller_safety_gate = (
    GeoCoolingControllerSafetyGate(
        controller=controller,
        state_cache=state_cache,
        subscription_manager=event_subscription_manager,
        event_bus=controller.event_bus,
        maximum_thermal_age_seconds=180.0,
        minimum_confidence=0.0,
        minimum_data_quality=0.0,
    )
)

setattr(
    controller,
    "brain_decision_publisher",
    brain_decision_publisher,
)

setattr(
    controller,
    "controller_safety_gate",
    controller_safety_gate,
)

# PATCH C015.0R1 — Execution Supervisor Bootstrap
execution_supervisor = GeoCoolingExecutionSupervisor(
    subscription_manager=event_subscription_manager,
    event_bus=controller.event_bus,
    history_capacity=500,
    event_capacity=1000,
)

setattr(
    controller,
    "execution_supervisor",
    execution_supervisor,
)

# PATCH C015.1R1 — Execution Analyzer Bootstrap
execution_analyzer = GeoCoolingExecutionAnalyzer(
    controller=controller,
    subscription_manager=event_subscription_manager,
    event_bus=controller.event_bus,
    history_capacity=500,
    event_capacity=2000,
)

setattr(
    controller,
    "execution_analyzer",
    execution_analyzer,
)

# PATCH C015.2R1 — Thermal Performance Analyzer Bootstrap
thermal_performance_analyzer = (
    GeoCoolingThermalPerformanceAnalyzer(
        controller=controller,
        thermal_engine=controller.thermal_engine,
        subscription_manager=event_subscription_manager,
        event_bus=controller.event_bus,
        history_capacity=500,
        event_capacity=1000,
    )
)

setattr(
    controller,
    "thermal_performance_analyzer",
    thermal_performance_analyzer,
)

# PATCH C015.3R1 — Brain Feedback Bootstrap
brain_feedback = GeoCoolingBrainFeedback(
    controller=controller,
    subscription_manager=event_subscription_manager,
    event_bus=controller.event_bus,
    engine=controller.engine,
    history_capacity=1000,
    rolling_window=20,
)

setattr(
    controller,
    "brain_feedback",
    brain_feedback,
)

# PATCH C016.0R1 — Operational Certification Bootstrap
operational_certification = OperationalCertificationEngine(
    controller=controller,
    event_bus=controller.event_bus,
    controller_command_bridge=globals().get(
        "controller_command_bridge"
    ),
    execution_supervisor=globals().get(
        "execution_supervisor"
    ),
    execution_analyzer=globals().get(
        "execution_analyzer"
    ),
    thermal_performance_analyzer=globals().get(
        "thermal_performance_analyzer"
    ),
    brain_feedback=globals().get(
        "brain_feedback"
    ),
    state_cache=getattr(
        controller,
        "state_cache",
        globals().get("state_cache"),
    ),
    history_capacity=500,
)

setattr(
    controller,
    "operational_certification",
    operational_certification,
)

# PATCH C016.1R1 — Sensor MQTT Discovery Bootstrap
sensor_mqtt_discovery = SensorMQTTDiscovery(
    event_bus=getattr(
        controller,
        "event_bus",
        globals().get("event_bus"),
    ),
    controller=controller,
    expected_sensor_count=4,
    history_capacity=1000,
)

sensor_mqtt_discovery.start()

setattr(
    controller,
    "sensor_mqtt_discovery",
    sensor_mqtt_discovery,
)

# PATCH C016.1R2 — Sensor Validation Bootstrap
sensor_validation = SensorValidationEngine(sensor_discovery=sensor_mqtt_discovery,event_bus=getattr(controller,"event_bus",globals().get("event_bus")),controller=controller)
setattr(controller,"sensor_validation",sensor_validation)

# PATCH C016.1R3 — MQTT Preflight Bootstrap
mqtt_preflight = MQTTPreflightCertification(
    sensor_discovery=sensor_mqtt_discovery,
    sensor_validation=sensor_validation,
    event_bus=getattr(
        controller,
        "event_bus",
        globals().get("event_bus"),
    ),
    controller=controller,
    history_capacity=500,
)
setattr(controller, "mqtt_preflight", mqtt_preflight)

# PATCH C016.1R4 — Hardware Certification Bootstrap
hardware_certification = HardwareCertificationEngine(
    controller=controller,
    sensor_discovery=sensor_mqtt_discovery,
    sensor_validation=sensor_validation,
    mqtt_preflight=mqtt_preflight,
    event_bus=getattr(
        controller,
        "event_bus",
        globals().get("event_bus"),
    ),
    history_capacity=500,
)
setattr(
    controller,
    "hardware_certification",
    hardware_certification,
)

# RELEASE 0.7.0 — Digital Twin + Water Test Framework
digital_twin = GeoCoolingDigitalTwin(
    controller=controller,
    event_bus=getattr(controller, "event_bus", None),
)
setattr(controller, "digital_twin", digital_twin)

digital_twin_calibration = DigitalTwinCalibration(
    controller=controller,
    digital_twin=digital_twin,
    forecast_engine=forecast_engine,
)
setattr(controller, "digital_twin_calibration", digital_twin_calibration)

efficiency_index = GeoCoolingEfficiencyIndex(
    controller=controller,
    digital_twin=digital_twin,
    calibration=digital_twin_calibration,
)
setattr(controller, "efficiency_index", efficiency_index)

drift_detector = GeoCoolingDriftDetector(
    efficiency_index=efficiency_index,
    calibration=digital_twin_calibration,
    digital_twin=digital_twin,
)
setattr(controller, "drift_detector", drift_detector)

assisted_calibration = AssistedCalibrationEngine(
    calibration=digital_twin_calibration,
    drift_detector=drift_detector,
    controller=controller,
)
setattr(controller, "assisted_calibration", assisted_calibration)

water_test_framework = GeoCoolingWaterTestFramework(
    controller=controller,
    digital_twin=digital_twin,
    event_bus=getattr(controller, "event_bus", None),
)
setattr(controller, "water_test_framework", water_test_framework)
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


@router.get("/brain/history")
def get_brain_history(limit: int = Query(default=200, ge=1, le=200)) -> dict:
    items = controller.brain.decision_history(limit)
    return {"count": len(items), "limit": limit, "items": items}


@router.get("/brain/metrics")
def get_brain_metrics() -> dict:
    return controller.brain.decision_metrics()


@router.get("/brain/journal")
def get_brain_journal(limit: int = Query(default=500, ge=1, le=5000)) -> list[dict]:
    return controller.brain.decision_journal(limit)


@router.get("/brain/journal/status")
def get_brain_journal_status() -> dict:
    return controller.brain.decision_journal_status()


@router.get("/brain/forecast")
def get_brain_forecast() -> dict:
    return forecast_engine.forecast()


@router.get("/brain/scenarios")
def get_brain_scenarios() -> dict:
    return forecast_engine.scenarios()


@router.get("/dashboard")
def get_operations_dashboard() -> dict:
    return operations_dashboard.snapshot()


@router.get("/prediction")
def get_prediction() -> dict:
    return controller.prediction_status()


@router.get("/home-assistant")
def get_home_assistant_status() -> dict:
    return controller.home_assistant_status()



def _hardware_requested_by(payload: dict | None) -> str:
    if payload is None:
        return "api"
    value = payload.get("requested_by", "api")
    return str(value).strip() or "api"


def _hardware_call(action, *, payload: dict | None = None) -> dict:
    try:
        return action(requested_by=_hardware_requested_by(payload))
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.get("/manual/hardware/status")
def manual_hardware_status() -> dict:
    try:
        return hardware_manual_control.status()
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/manual/arm")
def manual_hardware_arm(payload: dict = Body(default={})) -> dict:
    try:
        return hardware_manual_control.arm(
            confirmation=str(payload.get("confirmation", "")),
            requested_by=_hardware_requested_by(payload),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/manual/disarm")
def manual_hardware_disarm(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.disarm, payload=payload)


@router.post("/manual/valve/open")
def manual_hardware_valve_open(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.valve_open, payload=payload)


@router.post("/manual/valve/close")
def manual_hardware_valve_close(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.valve_close, payload=payload)


@router.post("/manual/pump/start")
def manual_hardware_pump_start(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.pump_start, payload=payload)


@router.post("/manual/pump/stop")
def manual_hardware_pump_stop(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.pump_stop, payload=payload)


@router.post("/manual/hardware/stop")
def manual_hardware_safe_stop(payload: dict = Body(default={})) -> dict:
    return _hardware_call(hardware_manual_control.safe_stop, payload=payload)

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

@router.get("/flight-recorder")
def get_geocooling_flight_recorder(
    limit: int = 300,
    errors_only: bool = False,
    include_controller: bool = True,
) -> dict:
    """Retourne l'historique circulaire du Controller."""

    return flight_recorder.status(
        limit=limit,
        errors_only=errors_only,
        include_controller=include_controller,
    )


@router.get("/flight-recorder/latest")
def get_geocooling_flight_recorder_latest() -> dict:
    """Retourne le dernier instantané du Controller."""

    return flight_recorder.latest()

@router.get("/events")
def get_geocooling_events(
    limit: int = 100,
    source: str | None = None,
    severity: str | None = None,
    event_type: str | None = None,
) -> dict:
    """Retourne la chronologie unifiée des événements GeoCooling."""

    return event_timeline.status(
        limit=limit,
        source=source,
        severity=severity,
        event_type=event_type,
    )


@router.get("/events/latest")
def get_geocooling_latest_event() -> dict:
    """Retourne le dernier événement GeoCooling connu."""

    return event_timeline.latest()

@router.get("/watchdog")
def get_geocooling_watchdog() -> dict:
    """Retourne l'analyse complète du Watchdog GeoCooling."""

    return watchdog.evaluate()


@router.get("/watchdog/alerts")
def get_geocooling_watchdog_alerts() -> dict:
    """Retourne uniquement les alertes actives du Watchdog."""

    return watchdog.alerts()

@router.get("/runtime")
def get_geocooling_runtime() -> dict:
    """Retourne l'état structurel du Runtime GeoCooling."""

    return runtime.status()

@router.get("/state-cache")
def get_geocooling_state_cache(
    include_controller: bool = True,
) -> dict:
    """Retourne le dernier état Controller mis en cache."""

    return state_cache.status(
        include_controller=include_controller
    )

@router.get("/snapshot-builder")
def get_geocooling_snapshot_builder() -> dict:
    """Expose les métriques du Snapshot Builder."""
    return controller.snapshot_builder.status()


# PATCH C011D.2 — Snapshot History API
@router.get("/snapshot-builder/history")
def get_geocooling_snapshot_builder_history(
    limit: int = Query(default=100, ge=1, le=500),
) -> dict[str, Any]:
    """Expose l'historique mémoire du Snapshot Builder."""

    return controller.snapshot_builder.history(
        limit=limit
    )


# PATCH C012.0 — Event Bus API
@router.get("/event-bus")
def get_geocooling_event_bus() -> dict[str, Any]:
    """Expose l'état du bus d'événements GeoCooling."""

    return controller.event_bus.status()

@router.get("/subscriptions")
def geocooling_subscriptions():
    return event_subscription_manager.status()


@router.get("/subscriptions/history")
def geocooling_subscriptions_history(
    limit: int = 20,
):
    normalized_limit = max(
        0,
        min(
            int(limit),
            200,
        ),
    )

    return {
        "overall": "OK",
        "component": "event_subscription_manager",
        "limit": normalized_limit,
        "history": event_subscription_manager.history(
            limit=normalized_limit,
        ),
    }

@router.get("/event-consumers")
def get_geocooling_event_consumers():
    return event_consumers.status()


@router.get("/event-consumers/history")
def get_geocooling_event_consumers_history(
    limit: int = Query(default=100, ge=1, le=500),
    event_type: str | None = None,
):
    return event_consumers.history(
        limit=limit,
        event_type=event_type,
    )

# PATCH C013.3R1 — Realtime Metrics API
@router.get("/realtime-metrics")
def get_geocooling_realtime_metrics():
    return realtime_metrics.status()


@router.get("/realtime-metrics/recent")
def get_geocooling_realtime_metrics_recent(
    limit: int = Query(default=100, ge=1, le=1000),
    event_type: str | None = None,
):
    return realtime_metrics.recent(
        limit=limit,
        event_type=event_type,
    )

# PATCH C014.0R1 — Controller Command Bridge API
@router.get("/controller-command-bridge")
def get_controller_command_bridge():
    return controller_command_bridge.status()


@router.get("/controller-command-bridge/history")
def get_controller_command_bridge_history(
    limit: int = Query(default=100, ge=1, le=500),
):
    return controller_command_bridge.history(
        limit=limit,
    )


@router.post("/controller-command-bridge/arm")
def arm_controller_command_bridge(
    confirmation: str = Body(
        embed=True,
        default="",
    ),
):
    if confirmation != "ARM_GEOCOOLING":
        raise HTTPException(
            status_code=400,
            detail=(
                "Confirmation requise : "
                "ARM_GEOCOOLING"
            ),
        )

    result = controller_command_bridge.arm()

    if result.get("overall") != "OK":
        raise HTTPException(
            status_code=409,
            detail=result,
        )

    return result


@router.post("/controller-command-bridge/disarm")
def disarm_controller_command_bridge():
    return controller_command_bridge.disarm()

# PATCH C014.1R2 — Brain Decision Publisher API
@router.get("/brain-decision-publisher")
def get_brain_decision_publisher():
    return brain_decision_publisher.status()


@router.get("/brain-decision-publisher/history")
def get_brain_decision_publisher_history(
    limit: int = Query(default=100, ge=1, le=500),
):
    return brain_decision_publisher.history(
        limit=limit,
    )


# PATCH C014.2R2 — Controller Safety Gate API
@router.get("/controller-safety-gate")
def get_controller_safety_gate():
    return controller_safety_gate.status()


@router.get("/controller-safety-gate/history")
def get_controller_safety_gate_history(
    limit: int = Query(default=100, ge=1, le=500),
):
    return controller_safety_gate.history(
        limit=limit,
    )


@router.get("/controller-safety-gate/evaluate")
def evaluate_controller_safety_gate(
    action: str = Query(default="start"),
):
    return controller_safety_gate.evaluate_current(
        action=action,
    )

# PATCH C015.0R1 — Execution Supervisor API
@router.get("/execution-supervisor")
def get_execution_supervisor():
    return execution_supervisor.status()


@router.get("/execution-supervisor/current")
def get_execution_supervisor_current():
    return execution_supervisor.current()


@router.get("/execution-supervisor/history")
def get_execution_supervisor_history(
    limit: int = 100,
):
    return execution_supervisor.history(
        limit=max(1, min(limit, 500)),
    )


@router.get("/execution-supervisor/events")
def get_execution_supervisor_events(
    limit: int = 100,
):
    return execution_supervisor.event_history(
        limit=max(1, min(limit, 1000)),
    )

# PATCH C015.1R1 — Execution Analyzer API
@router.get("/execution-analyzer")
def get_execution_analyzer():
    return execution_analyzer.status()


@router.get("/execution-analyzer/latest")
def get_execution_analyzer_latest():
    return execution_analyzer.latest()


@router.get("/execution-analyzer/history")
def get_execution_analyzer_history(
    limit: int = 100,
):
    return execution_analyzer.history(
        limit=max(1, min(limit, 500)),
    )


@router.get("/execution-analyzer/events")
def get_execution_analyzer_events(
    limit: int = 100,
):
    return execution_analyzer.event_history(
        limit=max(1, min(limit, 2000)),
    )

# PATCH C015.2R1 — Thermal Performance Analyzer API
@router.get("/thermal-performance-analyzer")
def get_thermal_performance_analyzer():
    return thermal_performance_analyzer.status()


@router.get("/thermal-performance-analyzer/latest")
def get_thermal_performance_analyzer_latest():
    return thermal_performance_analyzer.latest()


@router.get("/thermal-performance-analyzer/history")
def get_thermal_performance_analyzer_history(
    limit: int = 100,
):
    return thermal_performance_analyzer.history(
        limit=max(1, min(limit, 500)),
    )


@router.get("/thermal-performance-analyzer/events")
def get_thermal_performance_analyzer_events(
    limit: int = 100,
):
    return thermal_performance_analyzer.event_history(
        limit=max(1, min(limit, 1000)),
    )


@router.post("/thermal-performance-analyzer/analyze")
def analyze_thermal_performance():
    return thermal_performance_analyzer.analyze(
        trigger="api.manual",
    )

# PATCH C015.3R1 — Brain Feedback API
@router.get("/brain-feedback")
def get_brain_feedback():
    return brain_feedback.status()


@router.get("/brain-feedback/latest")
def get_brain_feedback_latest():
    return brain_feedback.latest()


@router.get("/brain-feedback/history")
def get_brain_feedback_history(
    limit: int = 100,
):
    return brain_feedback.history(
        limit=max(
            1,
            min(limit, 1000),
        ),
    )


@router.get("/brain-feedback/database-history")
def get_brain_feedback_database_history(
    limit: int = 100,
):
    return brain_feedback.database_history(
        limit=max(
            1,
            min(limit, 1000),
        ),
    )

# PATCH C016.0R1 — Operational Certification API
@router.get("/system-certification")
def get_system_certification():
    certification = (
        operational_certification.evaluate(
            trigger="http:get"
        )
    )

    return certification


@router.get("/system-certification/latest")
def get_system_certification_latest():
    return operational_certification.latest()


@router.get("/system-certification/history")
def get_system_certification_history(
    limit: int = 100,
):
    return operational_certification.history(
        limit=max(
            1,
            min(limit, 500),
        )
    )


@router.post("/system-certification/evaluate")
def evaluate_system_certification():
    return operational_certification.evaluate(
        trigger="http:post"
    )

# PATCH C016.1R1 — Sensor MQTT Discovery API
@router.get("/sensor-mqtt-discovery")
def get_sensor_mqtt_discovery():
    return sensor_mqtt_discovery.status()


@router.get("/sensor-mqtt-discovery/latest")
def get_sensor_mqtt_discovery_latest():
    return sensor_mqtt_discovery.latest()


@router.get("/sensor-mqtt-discovery/sensors")
def get_sensor_mqtt_discovery_sensors():
    return sensor_mqtt_discovery.sensors()


@router.get("/sensor-mqtt-discovery/topics")
def get_sensor_mqtt_discovery_topics(
    limit: int = 500,
):
    return sensor_mqtt_discovery.topics(
        limit=limit
    )


@router.get("/sensor-mqtt-discovery/history")
def get_sensor_mqtt_discovery_history(
    limit: int = 100,
):
    return sensor_mqtt_discovery.history(
        limit=limit
    )


@router.post("/sensor-mqtt-discovery/evaluate")
def evaluate_sensor_mqtt_discovery():
    return sensor_mqtt_discovery.evaluate(
        trigger="http:post"
    )

# PATCH C016.1R2 — Sensor Validation API
@router.get("/sensor-validation")
def get_sensor_validation(): return sensor_validation.status()

@router.get("/sensor-validation/latest")
def get_sensor_validation_latest(): return sensor_validation.latest()

@router.get("/sensor-validation/sensors")
def get_sensor_validation_sensors(): return sensor_validation.sensors()

@router.get("/sensor-validation/sensors/{sensor_id}/history")
def get_sensor_validation_sensor_history(sensor_id: str, limit: int = 100): return sensor_validation.sensor_history(sensor_id,limit=limit)

@router.get("/sensor-validation/history")
def get_sensor_validation_history(limit: int = 100): return sensor_validation.history(limit=limit)

@router.post("/sensor-validation/evaluate")
def evaluate_sensor_validation(): return sensor_validation.evaluate(trigger="http:post")

# PATCH C016.1R3 — MQTT Preflight API
@router.get("/mqtt-preflight")
def get_mqtt_preflight():
    return mqtt_preflight.status()


@router.get("/mqtt-preflight/latest")
def get_mqtt_preflight_latest():
    return mqtt_preflight.latest()


@router.get("/mqtt-preflight/contracts")
def get_mqtt_preflight_contracts():
    return mqtt_preflight.contracts()


@router.get("/mqtt-preflight/history")
def get_mqtt_preflight_history(limit: int = 100):
    return mqtt_preflight.history(limit=limit)


@router.post("/mqtt-preflight/evaluate")
def evaluate_mqtt_preflight():
    return mqtt_preflight.evaluate(trigger="http:post")

# PATCH C016.1R4 — Hardware Certification API
@router.get("/hardware-certification")
def get_hardware_certification():
    return hardware_certification.status()


@router.get("/hardware-certification/latest")
def get_hardware_certification_latest():
    return hardware_certification.latest()


@router.get("/hardware-certification/certificate")
def get_hardware_certification_certificate():
    return hardware_certification.certificate()


@router.get("/hardware-certification/history")
def get_hardware_certification_history(
    limit: int = 100,
):
    return hardware_certification.history(limit=limit)


@router.post("/hardware-certification/evaluate")
def evaluate_hardware_certification():
    return hardware_certification.evaluate(
        trigger="http:post"
    )

# RELEASE 0.7.0 — Digital Twin API
@router.get("/digital-twin")
def get_digital_twin():
    return digital_twin.status()


@router.get("/digital-twin/snapshot")
def get_digital_twin_snapshot(refresh: bool = True):
    return digital_twin.snapshot(refresh=refresh)


@router.post("/digital-twin/refresh")
def refresh_digital_twin():
    return digital_twin.refresh(trigger="http:post")


# PATCH C023.2 — Digital Twin calibration and prediction validation
@router.get("/digital-twin/model")
def get_digital_twin_model():
    return digital_twin_calibration.model()


@router.get("/digital-twin/calibration/status")
def get_digital_twin_calibration_status(evaluate_due: bool = True):
    return digital_twin_calibration.status(evaluate_due=evaluate_due)


@router.get("/digital-twin/calibration/history")
def get_digital_twin_calibration_history(limit: int = 100):
    return digital_twin_calibration.history(limit=limit)


@router.post("/digital-twin/calibration/capture")
def capture_digital_twin_prediction():
    return digital_twin_calibration.capture()


@router.post("/digital-twin/calibration/observe")
def observe_digital_twin_prediction(payload: dict = Body(...)):
    try:
        return digital_twin_calibration.observe(
            predicted_temperature_c=payload.get("predicted_temperature_c"),
            observed_temperature_c=payload.get("observed_temperature_c"),
            horizon_minutes=payload.get("horizon_minutes", 60),
            strategy=payload.get("strategy"),
            capture_id=payload.get("capture_id"),
            source=payload.get("source", "http"),
        )
    except (TypeError, ValueError) as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# PATCH C023.3 — GeoCooling Efficiency Index
@router.get("/performance/gei")
def get_geocooling_efficiency_index(persist: bool = True):
    return efficiency_index.calculate(persist=persist)


@router.get("/performance/gei/history")
def get_geocooling_efficiency_history(limit: int = Query(default=100, ge=1, le=500)):
    return efficiency_index.history(limit=limit)


@router.get("/performance/gei/status")
def get_geocooling_efficiency_status():
    return efficiency_index.status()


# PATCH C023.4 — Détection des dérives
@router.get("/performance/drift")
def get_geocooling_drift_analysis(persist: bool = True):
    return drift_detector.analyze(persist=persist)


@router.get("/performance/drift/history")
def get_geocooling_drift_history(limit: int = Query(default=100, ge=1, le=500)):
    return drift_detector.history(limit=limit)


@router.get("/performance/drift/status")
def get_geocooling_drift_status():
    return drift_detector.status()


# PATCH C023.5 — Auto-calibration assistée (aucune application automatique)
@router.get("/performance/calibration/recommendations")
def get_assisted_calibration_recommendations(persist: bool = False):
    return assisted_calibration.recommendations(persist=persist)


@router.get("/performance/calibration/history")
def get_assisted_calibration_history(limit: int = Query(default=100, ge=1, le=500)):
    return assisted_calibration.history(limit=limit)


@router.get("/performance/calibration/status")
def get_assisted_calibration_status():
    return assisted_calibration.status()


@router.post("/performance/calibration/decision")
def post_assisted_calibration_decision(payload: dict):
    return assisted_calibration.decide(
        proposal=payload.get("proposal"),
        decision=payload.get("decision", ""),
        note=payload.get("note"),
        decided_by=payload.get("decided_by", "operator"),
    )



# PATCH C024.3 — Runtime profiling (non intrusif)
runtime_profiler = GeoCoolingRuntimeProfiler()

# SPRINT C025 — Operations Suite 1.0
alarm_engine = GeoCoolingAlarmEngine()
operations_suite = GeoCoolingOperationsSuite(
    controller=controller,
    health_manager=health_manager,
    commissioning_manager=commissioning_manager,
    commissioning_test_manager=commissioning_test_manager,
    hardware_manual_control=hardware_manual_control,
    operations_dashboard=operations_dashboard,
    integration_audit=integration_audit,
    runtime_profiler=runtime_profiler,
    efficiency_index=efficiency_index,
    drift_detector=drift_detector,
    assisted_calibration=assisted_calibration,
    digital_twin_calibration=digital_twin_calibration,
    hardware_certification=hardware_certification,
    alarm_engine=alarm_engine,
)
industrial_hardening = GeoCoolingIndustrialHardening(
    controller=controller,
    watchdog=watchdog,
    runtime=runtime,
    integration_audit=integration_audit,
    runtime_profiler=runtime_profiler,
    operations_suite=operations_suite,
    hardware_manual_control=hardware_manual_control,
)
setattr(controller, "industrial_hardening", industrial_hardening)
industrial_platform = GeoCoolingIndustrialPlatform(
    controller=controller,
    hardening=industrial_hardening,
    physical_factory=WaveshareModbusDriver,
)
setattr(controller, "industrial_platform", industrial_platform)
for _target, _method, _component in (
    (controller.brain, "evaluate", "brain"),
    (forecast_engine, "forecast", "forecast"),
    (forecast_engine, "scenarios", "forecast"),
    (operations_dashboard, "snapshot", "dashboard"),
    (efficiency_index, "calculate", "efficiency_index"),
    (drift_detector, "analyze", "drift_detector"),
    (assisted_calibration, "recommendations", "assisted_calibration"),
    (integration_audit, "evaluate", "integration_audit"),
):
    runtime_profiler.instrument(_target, _method, component=_component)


# RELEASE 0.7.0 — Water Test Framework API
@router.get("/water-test")
def get_water_test_status():
    return water_test_framework.status()


@router.get("/water-test/scenarios")
def get_water_test_scenarios():
    return water_test_framework.scenarios()


@router.get("/water-test/session")
def get_water_test_session(session_id: str | None = None):
    try:
        return water_test_framework.session(session_id)
    except WaterTestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.get("/water-test/history")
def get_water_test_history(limit: int = Query(default=100, ge=1, le=1000)):
    return water_test_framework.history(limit=limit)


@router.get("/water-test/report/{session_id}")
def get_water_test_report(session_id: str):
    try:
        return water_test_framework.report(session_id)
    except WaterTestError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc


@router.post("/water-test/create")
def create_water_test(payload: dict[str, Any] = Body(...)):
    try:
        return water_test_framework.create(
            scenario_id=str(payload.get("scenario_id", "")),
            operator=str(payload.get("operator", "")),
            notes=str(payload.get("notes", "")),
        )
    except WaterTestError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/water-test/start")
def start_water_test(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    try:
        return water_test_framework.start(session_id=payload.get("session_id"))
    except WaterTestError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/water-test/simulate-step")
def simulate_water_test_step(payload: dict[str, Any] = Body(...)):
    try:
        return water_test_framework.simulate_step(
            session_id=payload.get("session_id"),
            action=str(payload.get("action", "")),
            values=payload.get("values") or {},
        )
    except (WaterTestError, TypeError, ValueError) as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/water-test/finish")
def finish_water_test(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    try:
        return water_test_framework.finish(
            session_id=payload.get("session_id"),
            result=str(payload.get("result", "PASS")),
            notes=str(payload.get("notes", "")),
        )
    except WaterTestError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/water-test/cancel")
def cancel_water_test(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    try:
        return water_test_framework.cancel(
            session_id=payload.get("session_id"),
            reason=str(payload.get("reason", "Annulation opérateur")),
        )
    except WaterTestError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc



# PATCH C024.1 — Audit d'intégration pré-commissioning (lecture seule)
@router.get("/integration-audit")
def get_geocooling_integration_audit(refresh: bool = True):
    return integration_audit.evaluate() if refresh else integration_audit.status()

@router.get("/integration-audit/status")
def get_geocooling_integration_audit_status():
    return integration_audit.status()


# PATCH C024.3 — Profilage runtime (lecture seule)
@router.get("/performance/runtime")
def get_geocooling_runtime_profile():
    return runtime_profiler.snapshot()

@router.get("/performance/runtime/history")
def get_geocooling_runtime_history(limit: int = Query(default=200, ge=1, le=2000)):
    items = runtime_profiler.history(limit=limit)
    return {"count": len(items), "limit": limit, "items": items}

@router.get("/performance/runtime/status")
def get_geocooling_runtime_status():
    return runtime_profiler.status()


# SPRINT C025 — Operations Suite 1.0
@router.get("/operations-center")
def get_geocooling_operations_center():
    return operations_suite.snapshot()

@router.get("/health")
def get_geocooling_operations_health():
    return health_manager.status()

@router.get("/readiness")
def get_geocooling_readiness():
    return operations_suite.readiness()

@router.get("/readiness/status")
def get_geocooling_readiness_status():
    return operations_suite.readiness()

@router.get("/readiness/checklist")
def get_geocooling_readiness_checklist():
    return operations_suite.checklist()

@router.get("/alarms")
def get_geocooling_alarms():
    operations_suite.snapshot()
    return alarm_engine.snapshot()

@router.get("/alarms/history")
def get_geocooling_alarm_history(limit: int = Query(default=200, ge=1, le=2000)):
    items = alarm_engine.history(limit=limit)
    return {"count": len(items), "limit": limit, "items": items}

@router.post("/alarms/{alarm_id}/acknowledge")
def acknowledge_geocooling_alarm(alarm_id: str, payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    try:
        return alarm_engine.acknowledge(alarm_id, str(payload.get("operator", "operator")), str(payload.get("note", "")))
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc

@router.get("/commissioning/report")
def get_geocooling_commissioning_report():
    return operations_suite.report()


# SPRINT H001 — Industrial hardening
@router.get("/hardening")
def get_geocooling_hardening_status():
    return industrial_hardening.status()

@router.get("/hardening/probe")
def probe_geocooling_components():
    return industrial_hardening.probe()

@router.get("/hardening/watchdog")
def get_geocooling_hardening_watchdog():
    probe = industrial_hardening.probe()
    return industrial_hardening.evaluate_safe_mode(probe)

@router.post("/hardening/safe-mode")
def activate_geocooling_safe_mode(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_hardening.safe_mode.activate(
            reason=str(payload.get("reason", "")),
            activated_by=str(payload.get("operator", "operator")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/hardening/safe-mode/clear")
def clear_geocooling_safe_mode(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    return industrial_hardening.safe_mode.clear(str(payload.get("operator", "operator")))

@router.get("/hardening/transactions")
def get_geocooling_transaction_history(limit: int = Query(default=100, ge=1, le=1000)):
    items = industrial_hardening.transactions.history(limit)
    return {"count": len(items), "items": items}

@router.post("/hardening/transactions/dry-run")
def dry_run_geocooling_transaction(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    names = payload.get("steps") or ["validate", "prepare", "commit"]
    steps = [TransactionStep(name=str(name), action=lambda: None) for name in names]
    return industrial_hardening.transactions.execute(str(payload.get("name", "api-dry-run")), steps, dry_run=True)

@router.get("/software-certification")
def get_geocooling_software_certification(refresh: bool = True):
    return industrial_hardening.certification(refresh=refresh)

# SPRINT H002 — Lifecycle, startup self-test and restart recovery
@router.get("/hardening/lifecycle")
def get_geocooling_hardening_lifecycle():
    return industrial_hardening.lifecycle.snapshot()

@router.get("/hardening/lifecycle/history")
def get_geocooling_hardening_lifecycle_history(limit: int = Query(default=100, ge=1, le=1000)):
    items = industrial_hardening.lifecycle.history(limit)
    return {"count": len(items), "items": items}

@router.get("/hardening/startup-self-test")
def get_geocooling_startup_self_test(refresh: bool = False):
    return industrial_hardening.run_startup_self_test() if refresh else industrial_hardening.startup_status()

@router.get("/hardening/recovery")
def get_geocooling_recovery_report():
    return industrial_hardening.recovery_report()


# MACRO SPRINT H003-H006 — Observability, hardware gateway, Brain V2, pre-certification
@router.get("/industrial-platform/diagnostics")
def get_industrial_platform_diagnostics():
    return industrial_platform.diagnostics()

@router.get("/industrial-platform/events")
def get_industrial_platform_events(limit: int = Query(default=200, ge=1, le=2000), minimum_level: str | None = None):
    items = industrial_platform.events.history(limit, minimum_level=minimum_level)
    return {"count": len(items), "items": items}

@router.get("/industrial-platform/metrics")
def get_industrial_platform_metrics():
    return industrial_platform.events.metrics()

@router.get("/industrial-platform/hardware")
def get_industrial_platform_hardware():
    return industrial_platform.hardware.status()

@router.post("/industrial-platform/hardware/dry-run")
def post_industrial_platform_hardware_dry_run(payload: dict[str, Any] = Body(...)):
    return industrial_platform.hardware.dry_run(str(payload.get("command", "")))

@router.get("/industrial-platform/brain-v2")
def get_industrial_platform_brain_v2():
    return industrial_platform.brain_v2.analyze(controller.brain_status(), controller.thermal_status())

@router.get("/industrial-platform/pre-certification")
def get_industrial_platform_pre_certification():
    return industrial_platform.certification()
