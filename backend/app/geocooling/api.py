from typing import Any
from datetime import datetime, timezone
import csv
import io
import json

from fastapi import APIRouter, Body, HTTPException, Query
from fastapi.responses import JSONResponse, Response

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
from app.geocooling.industrial_platform import GeoCoolingIndustrialPlatform, utc_now_iso
from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver
from app.geocooling.brain_v2.api import router as brain_v2_router

router = APIRouter(prefix="/geocooling", tags=["GeoCooling"])
router.include_router(brain_v2_router)
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


# C020.1R4 DIGITAL TWIN LIVE FEED
def _c020_digital_twin_snapshot_payload(payload: dict[str, Any]) -> dict[str, Any]:
    aliases = {
        "indoor_temperature_c": ("indoor_temperature_c", "indoor", "indoor_temperature"),
        "upstairs_temperature_c": ("upstairs_temperature_c", "upstairs", "upstairs_temperature"),
        "outdoor_temperature_c": ("outdoor_temperature_c", "outdoor", "outdoor_temperature"),
        "indoor_humidity_percent": ("indoor_humidity_percent", "humidity", "indoor_humidity"),
        "floor_surface_temperature_c": ("floor_surface_temperature_c", "surface", "surface_temperature"),
        "supply_temperature_c": ("supply_temperature_c", "supply", "supply_temperature"),
        "return_temperature_c": ("return_temperature_c", "return", "return_temperature"),
        "source_in_temperature_c": ("source_in_temperature_c", "source_in", "source_in_temperature"),
        "source_out_temperature_c": ("source_out_temperature_c", "source_out", "source_out_temperature"),
        "flow_l_min": ("flow_l_min", "flow", "flow_rate_l_min"),
        "pump_running": ("pump_running", "pump"),
        "valve_open": ("valve_open", "valve"),
        "measured_at": ("measured_at", "timestamp", "captured_at"),
    }

    normalized: dict[str, Any] = {}
    for target, candidates in aliases.items():
        for candidate in candidates:
            if candidate in payload and payload[candidate] is not None:
                normalized[target] = payload[candidate]
                break
    return normalized


@router.put("/thermal-snapshot")
def put_thermal_snapshot(payload: dict[str, Any] = Body(...)) -> dict:
    try:
        result = controller.ingest_thermal_snapshot(payload)
        # C020.1R5R11 — feed both runtime Digital Twin instances
        normalized_twin_payload = _c020_digital_twin_snapshot_payload(payload)

        digital_twin.update(normalized_twin_payload)
        industrial_platform.digital_twin.update(normalized_twin_payload)

        return result
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




# ============================================================================
# C021.1 — UNIFIED BRAIN DASHBOARD API
# ============================================================================

def _c021_safe_section(
    name: str,
    provider,
    *,
    default=None,
) -> dict[str, Any]:
    """
    Exécute un fournisseur de données sans rendre indisponible le dashboard
    si un sous-système est momentanément absent ou incompatible.

    Aucun appel matériel ni aucune commande ne sont exécutés ici.
    """
    try:
        value = provider()

        if value is None:
            value = default if default is not None else {}

        return {
            "available": True,
            "data": value,
            "error": None,
        }

    except Exception as exc:
        return {
            "available": False,
            "data": default if default is not None else {},
            "error": {
                "component": name,
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _c021_extract_alerts(sections: dict[str, dict[str, Any]]) -> list[dict[str, Any]]:
    alerts: list[dict[str, Any]] = []

    for section_name, section in sections.items():
        if not section.get("available", False):
            error = section.get("error") or {}
            alerts.append(
                {
                    "level": "WARNING",
                    "code": "COMPONENT_UNAVAILABLE",
                    "component": section_name,
                    "message": error.get("message") or "Composant indisponible",
                }
            )

    twin = sections.get("digital_twin", {}).get("data") or {}

    condensation_risk = twin.get("condensation_risk")
    if condensation_risk in {"WATCH", "HIGH", "CRITICAL"}:
        alerts.append(
            {
                "level": (
                    "CRITICAL"
                    if condensation_risk == "CRITICAL"
                    else "WARNING"
                ),
                "code": "CONDENSATION_RISK",
                "component": "digital_twin",
                "message": (
                    "Risque de condensation détecté : "
                    f"{condensation_risk}"
                ),
                "margin_c": twin.get("condensation_margin_c"),
            }
        )

    observations = twin.get("observations") or []
    for observation in observations:
        alerts.append(
            {
                "level": "WARNING",
                "code": str(observation),
                "component": "digital_twin",
                "message": str(observation).replace("_", " ").title(),
            }
        )

    thermal = sections.get("thermal", {}).get("data") or {}
    safety = thermal.get("safety") if isinstance(thermal, dict) else None

    if isinstance(safety, dict) and safety.get("safe") is False:
        alerts.append(
            {
                "level": "CRITICAL",
                "code": "THERMAL_SAFETY_BLOCK",
                "component": "thermal",
                "message": safety.get("reason") or "Sécurité thermique active",
            }
        )

    return alerts


@router.get("/brain/dashboard")
def get_brain_dashboard() -> dict[str, Any]:
    """
    Endpoint unifié destiné à Home Assistant.

    Lecture seule :
    - aucune publication MQTT ;
    - aucune écriture Modbus ;
    - aucune commande de pompe ou de vanne ;
    - aucun changement de mode ;
    - aucun accès matériel forcé.
    """

    generated_at = datetime.now(timezone.utc).isoformat()

    sections: dict[str, dict[str, Any]] = {
        "system": _c021_safe_section(
            "system",
            lambda: controller.status(),
        ),
        "brain": _c021_safe_section(
            "brain",
            lambda: controller.brain_status(),
        ),
        "decision_engine": _c021_safe_section(
            "decision_engine",
            lambda: _c0213_build_decision(),
        ),
        "digital_twin": _c021_safe_section(
            "digital_twin",
            lambda: digital_twin.snapshot(refresh=False),
        ),
        "forecast": _c021_safe_section(
            "forecast",
            lambda: forecast_engine.forecast(),
        ),
        "scenarios": _c021_safe_section(
            "scenarios",
            lambda: forecast_engine.scenarios(),
            default={},
        ),
        "thermal": _c021_safe_section(
            "thermal",
            lambda: controller.thermal_status(),
        ),
        "prediction": _c021_safe_section(
            "prediction",
            lambda: controller.prediction_status(),
        ),
        "hardware": _c021_safe_section(
            "hardware",
            lambda: controller.diagnostics(),
        ),
        "home_assistant": _c021_safe_section(
            "home_assistant",
            lambda: controller.home_assistant_status(),
        ),
        "operations": _c021_safe_section(
            "operations",
            lambda: operations_dashboard.snapshot(),
        ),
    }

    alerts = _c021_extract_alerts(sections)

    available_count = sum(
        1 for section in sections.values()
        if section.get("available", False)
    )
    total_count = len(sections)

    digital_twin_data = sections["digital_twin"].get("data") or {}
    system_data = sections["system"].get("data") or {}
    brain_data = sections["brain"].get("data") or {}

    return {
        "generated_at": generated_at,
        "version": "C021.1-BRAIN-DASHBOARD-1.0",
        "read_only": True,
        "hardware_touched": False,
        "health": {
            "status": (
                "READY"
                if available_count == total_count
                else "DEGRADED"
            ),
            "available_components": available_count,
            "total_components": total_count,
            "availability_percent": round(
                available_count * 100 / total_count,
                1,
            ),
            "alert_count": len(alerts),
        },
        "summary": {
            "system_status": (
                system_data.get("status")
                or system_data.get("mode")
                or "UNKNOWN"
            ),
            "brain_status": (
                brain_data.get("status")
                or brain_data.get("decision")
                or "UNKNOWN"
            ),
            "thermal_state": digital_twin_data.get("thermal_state"),
            "digital_twin_status": digital_twin_data.get("status"),
            "confidence_percent": digital_twin_data.get(
                "confidence_percent"
            ),
            "data_quality_percent": digital_twin_data.get(
                "data_quality_percent"
            ),
            "condensation_risk": digital_twin_data.get(
                "condensation_risk"
            ),
            "condensation_margin_c": digital_twin_data.get(
                "condensation_margin_c"
            ),
            "pump_running": digital_twin_data.get("pump_running"),
            "valve_open": digital_twin_data.get("valve_open"),
            "active_cooling": digital_twin_data.get("active_cooling"),
        },
        "sections": sections,
        "alerts": alerts,
    }




# ============================================================================
# C021.2 — UNIFIED HISTORIAN API
# ============================================================================

_C0212_HISTORIAN_VERSION = "C021.2-UNIFIED-HISTORIAN-1.0"


def _c0212_safe_call(provider, default):
    try:
        value = provider()
        return {
            "available": True,
            "data": default if value is None else value,
            "error": None,
        }
    except Exception as exc:
        return {
            "available": False,
            "data": default,
            "error": {
                "type": type(exc).__name__,
                "message": str(exc),
            },
        }


def _c0212_extract_items(value: Any) -> list[dict[str, Any]]:
    """
    Accepte les formes historiques déjà utilisées dans le projet :
    - liste directe ;
    - {"items": [...]}
    - {"history": [...]}
    - {"events": [...]}
    - {"records": [...]}
    """
    if isinstance(value, list):
        return [
            item for item in value
            if isinstance(item, dict)
        ]

    if not isinstance(value, dict):
        return []

    for key in ("items", "history", "events", "records", "samples"):
        items = value.get(key)
        if isinstance(items, list):
            return [
                item for item in items
                if isinstance(item, dict)
            ]

    return []


def _c0212_timestamp(record: dict[str, Any]) -> str | None:
    for key in (
        "timestamp",
        "generated_at",
        "measured_at",
        "created_at",
        "recorded_at",
        "decided_at",
        "observed_at",
        "time",
    ):
        value = record.get(key)
        if value is not None:
            return str(value)

    return None


def _c0212_sort_records(
    records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    return sorted(
        records,
        key=lambda item: _c0212_timestamp(item) or "",
        reverse=True,
    )


def _c0212_collect_history(limit: int) -> dict[str, Any]:
    thermal_raw = _c0212_safe_call(
        lambda: controller.thermal_history(limit),
        [],
    )

    brain_raw = _c0212_safe_call(
        lambda: controller.brain.decision_journal(limit),
        [],
    )

    controller_raw = _c0212_safe_call(
        lambda: controller.history(limit),
        [],
    )

    thermal_items = _c0212_sort_records(
        _c0212_extract_items(thermal_raw["data"])
    )[:limit]

    brain_items = _c0212_sort_records(
        _c0212_extract_items(brain_raw["data"])
    )[:limit]

    controller_items = _c0212_sort_records(
        _c0212_extract_items(controller_raw["data"])
    )[:limit]

    return {
        "thermal": {
            "available": thermal_raw["available"],
            "count": len(thermal_items),
            "items": thermal_items,
            "error": thermal_raw["error"],
        },
        "brain": {
            "available": brain_raw["available"],
            "count": len(brain_items),
            "items": brain_items,
            "error": brain_raw["error"],
        },
        "controller": {
            "available": controller_raw["available"],
            "count": len(controller_items),
            "items": controller_items,
            "error": controller_raw["error"],
        },
    }


def _c0212_latest_record(
    records: list[dict[str, Any]],
) -> dict[str, Any] | None:
    if not records:
        return None

    return _c0212_sort_records(records)[0]


def _c0212_flatten_csv_value(value: Any) -> Any:
    if value is None:
        return ""

    if isinstance(value, (str, int, float, bool)):
        return value

    return json.dumps(
        value,
        ensure_ascii=False,
        separators=(",", ":"),
        default=str,
    )


@router.get("/historian/status")
def get_historian_status() -> dict[str, Any]:
    history = _c0212_collect_history(limit=1)

    available_sources = sum(
        1
        for source in history.values()
        if source.get("available") is True
    )

    total_sources = len(history)

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": _C0212_HISTORIAN_VERSION,
        "status": (
            "READY"
            if available_sources == total_sources
            else "DEGRADED"
        ),
        "read_only": True,
        "hardware_touched": False,
        "available_sources": available_sources,
        "total_sources": total_sources,
        "sources": {
            name: {
                "available": data.get("available"),
                "count": data.get("count"),
                "error": data.get("error"),
            }
            for name, data in history.items()
        },
    }


@router.get("/historian/latest")
def get_historian_latest() -> dict[str, Any]:
    history = _c0212_collect_history(limit=1)

    digital_twin_result = _c0212_safe_call(
        lambda: digital_twin.snapshot(refresh=False),
        {},
    )

    thermal_status_result = _c0212_safe_call(
        lambda: controller.thermal_status(),
        {},
    )

    brain_status_result = _c0212_safe_call(
        lambda: controller.brain_status(),
        {},
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": _C0212_HISTORIAN_VERSION,
        "read_only": True,
        "hardware_touched": False,
        "latest": {
            "thermal": _c0212_latest_record(
                history["thermal"]["items"]
            ),
            "brain": _c0212_latest_record(
                history["brain"]["items"]
            ),
            "controller": _c0212_latest_record(
                history["controller"]["items"]
            ),
            "digital_twin": digital_twin_result["data"],
            "thermal_status": thermal_status_result["data"],
            "brain_status": brain_status_result["data"],
        },
        "availability": {
            "digital_twin": digital_twin_result["available"],
            "thermal_status": thermal_status_result["available"],
            "brain_status": brain_status_result["available"],
        },
    }


@router.get("/historian/history")
def get_historian_history(
    limit: int = Query(default=200, ge=1, le=5000),
    stream: str = Query(default="all"),
) -> dict[str, Any]:
    normalized_stream = stream.strip().lower()

    allowed_streams = {
        "all",
        "thermal",
        "brain",
        "controller",
    }

    if normalized_stream not in allowed_streams:
        raise HTTPException(
            status_code=422,
            detail=(
                "stream doit être l’une des valeurs suivantes : "
                "all, thermal, brain, controller"
            ),
        )

    history = _c0212_collect_history(limit=limit)

    if normalized_stream == "all":
        selected = history
    else:
        selected = {
            normalized_stream: history[normalized_stream]
        }

    total_records = sum(
        section.get("count", 0)
        for section in selected.values()
    )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": _C0212_HISTORIAN_VERSION,
        "read_only": True,
        "hardware_touched": False,
        "stream": normalized_stream,
        "limit": limit,
        "total_records": total_records,
        "streams": selected,
    }


@router.get("/historian/export")
def export_historian_csv(
    limit: int = Query(default=1000, ge=1, le=5000),
    stream: str = Query(default="thermal"),
) -> Response:
    normalized_stream = stream.strip().lower()

    allowed_streams = {
        "thermal",
        "brain",
        "controller",
    }

    if normalized_stream not in allowed_streams:
        raise HTTPException(
            status_code=422,
            detail=(
                "stream doit être l’une des valeurs suivantes : "
                "thermal, brain, controller"
            ),
        )

    history = _c0212_collect_history(limit=limit)
    records = history[normalized_stream]["items"]

    field_names: list[str] = ["historian_stream"]

    dynamic_fields = sorted(
        {
            str(key)
            for record in records
            for key in record.keys()
        }
    )

    field_names.extend(
        field
        for field in dynamic_fields
        if field != "historian_stream"
    )

    output = io.StringIO()
    writer = csv.DictWriter(
        output,
        fieldnames=field_names,
        extrasaction="ignore",
    )

    writer.writeheader()

    for record in reversed(records):
        row = {
            "historian_stream": normalized_stream,
        }

        row.update(
            {
                str(key): _c0212_flatten_csv_value(value)
                for key, value in record.items()
            }
        )

        writer.writerow(row)

    filename = (
        f"geocooling-{normalized_stream}-"
        f"{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}.csv"
    )

    return Response(
        content=output.getvalue(),
        media_type="text/csv; charset=utf-8",
        headers={
            "Content-Disposition": (
                f'attachment; filename="{filename}"'
            ),
            "X-GeoCooling-Version": _C0212_HISTORIAN_VERSION,
            "X-Hardware-Touched": "false",
        },
    )




# ============================================================================
# C021.3 — EXPLAINABLE DECISION ENGINE
# ============================================================================

_C0213_DECISION_ENGINE_VERSION = "C021.3-DECISION-ENGINE-1.0"


def _c0213_find_value(
    value: Any,
    keys: tuple[str, ...],
) -> Any:
    """
    Recherche récursivement la première valeur correspondant à l’une
    des clés demandées dans une structure JSON.
    """
    if isinstance(value, dict):
        for key in keys:
            if key in value and value[key] is not None:
                return value[key]

        for child in value.values():
            found = _c0213_find_value(child, keys)
            if found is not None:
                return found

    elif isinstance(value, list):
        for child in value:
            found = _c0213_find_value(child, keys)
            if found is not None:
                return found

    return None


def _c0213_float(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        result = float(value)
    except (TypeError, ValueError):
        return None

    if result != result:
        return None

    return result


def _c0213_bool(value: Any) -> bool | None:
    if isinstance(value, bool):
        return value

    if isinstance(value, (int, float)):
        return bool(value)

    if isinstance(value, str):
        normalized = value.strip().lower()

        if normalized in {"true", "on", "yes", "1", "running", "open"}:
            return True

        if normalized in {"false", "off", "no", "0", "stopped", "closed"}:
            return False

    return None


def _c0213_build_decision() -> dict[str, Any]:
    brain_result = _c0212_safe_call(
        lambda: controller.brain_status(),
        {},
    )

    forecast_result = _c0212_safe_call(
        lambda: forecast_engine.forecast(),
        {},
    )

    twin_result = _c0212_safe_call(
        lambda: digital_twin.snapshot(refresh=False),
        {},
    )

    prediction_result = _c0212_safe_call(
        lambda: controller.prediction_status(),
        {},
    )

    system_result = _c0212_safe_call(
        lambda: controller.status(),
        {},
    )

    brain = brain_result["data"] or {}
    forecast = forecast_result["data"] or {}
    twin = twin_result["data"] or {}
    prediction = prediction_result["data"] or {}
    system = system_result["data"] or {}

    existing_decision = _c0213_find_value(
        brain,
        (
            "decision",
            "action",
            "recommended_action",
            "command",
            "state",
        ),
    )

    existing_reason = _c0213_find_value(
        brain,
        (
            "reason",
            "explanation",
            "rationale",
            "decision_reason",
        ),
    )

    existing_confidence = _c0213_float(
        _c0213_find_value(
            brain,
            (
                "confidence_percent",
                "confidence",
                "score",
                "decision_confidence",
            ),
        )
    )

    indoor_temperature = _c0213_float(
        twin.get("indoor_air_temperature_c")
    )

    outdoor_temperature = _c0213_float(
        twin.get("outdoor_air_temperature_c")
    )

    floor_surface_temperature = _c0213_float(
        twin.get("floor_surface_temperature_c")
    )

    supply_temperature = _c0213_float(
        twin.get("supply_temperature_c")
    )

    return_temperature = _c0213_float(
        twin.get("return_temperature_c")
    )

    flow_l_min = _c0213_float(
        twin.get("flow_l_min")
    )

    condensation_margin = _c0213_float(
        twin.get("condensation_margin_c")
    )

    condensation_risk = (
        twin.get("condensation_risk")
        or "UNKNOWN"
    )

    cold_storage = _c0213_float(
        twin.get("cold_storage_percent")
    )

    pump_running = _c0213_bool(
        twin.get("pump_running")
    )

    valve_open = _c0213_bool(
        twin.get("valve_open")
    )

    active_cooling = _c0213_bool(
        twin.get("active_cooling")
    )

    predicted_outdoor_max = _c0213_float(
        _c0213_find_value(
            forecast,
            (
                "maximum_temperature_c",
                "max_temperature_c",
                "temperature_max_c",
                "outdoor_max_c",
                "daily_high_c",
                "forecast_max_c",
            ),
        )
    )

    predicted_indoor = _c0213_float(
        _c0213_find_value(
            prediction,
            (
                "predicted_indoor_temperature_c",
                "indoor_temperature_prediction_c",
                "predicted_temperature_c",
                "forecast_indoor_c",
            ),
        )
    )

    start_at = _c0213_find_value(
        brain,
        (
            "start_at",
            "start_time",
            "optimal_start_at",
            "recommended_start_at",
        ),
    )

    stop_at = _c0213_find_value(
        brain,
        (
            "stop_at",
            "stop_time",
            "optimal_stop_at",
            "recommended_stop_at",
        ),
    )

    reasons: list[str] = []
    blockers: list[str] = []
    recommendations: list[str] = []
    conditions_to_start: list[str] = []
    conditions_to_stop: list[str] = []

    if existing_reason:
        if isinstance(existing_reason, list):
            reasons.extend(str(item) for item in existing_reason)
        else:
            reasons.append(str(existing_reason))

    if indoor_temperature is not None:
        reasons.append(
            f"Température intérieure mesurée : "
            f"{indoor_temperature:.1f} °C"
        )

    if outdoor_temperature is not None:
        reasons.append(
            f"Température extérieure mesurée : "
            f"{outdoor_temperature:.1f} °C"
        )

    if predicted_outdoor_max is not None:
        reasons.append(
            f"Température extérieure maximale prévue : "
            f"{predicted_outdoor_max:.1f} °C"
        )

    if predicted_indoor is not None:
        reasons.append(
            f"Température intérieure prédite : "
            f"{predicted_indoor:.1f} °C"
        )

    if cold_storage is not None:
        reasons.append(
            f"Stockage de froid estimé : "
            f"{cold_storage:.1f} %"
        )

    if condensation_margin is not None:
        reasons.append(
            f"Marge avant condensation : "
            f"{condensation_margin:.2f} °C"
        )

    if condensation_risk in {"HIGH", "CRITICAL"}:
        blockers.append(
            "Risque de condensation incompatible avec "
            "un refroidissement normal."
        )

    if condensation_margin is not None and condensation_margin < 3.0:
        blockers.append(
            "Marge de condensation inférieure à 3 °C."
        )

    if pump_running is True and valve_open is False:
        blockers.append(
            "Pompe active alors que la vanne est fermée."
        )

    if (
        pump_running is True
        and flow_l_min is not None
        and flow_l_min <= 0
    ):
        blockers.append(
            "Pompe active sans débit hydraulique mesuré."
        )

    conditions_to_start.extend(
        [
            "Sécurité thermique autorisée.",
            "Marge de condensation suffisante.",
            "Vanne disponible et circuit hydraulique cohérent.",
            "Demande de refroidissement confirmée par le Brain.",
        ]
    )

    conditions_to_stop.extend(
        [
            "Température intérieure revenue sous la consigne d’arrêt.",
            "Stockage de froid suffisant.",
            "Marge de condensation devenue insuffisante.",
            "Anomalie hydraulique ou matérielle détectée.",
        ]
    )

    normalized_existing = (
        str(existing_decision).strip().upper()
        if existing_decision is not None
        else ""
    )

    if blockers:
        decision = "BLOCK_COOLING"
        decision_class = "SAFETY"
        recommendations.append(
            "Maintenir pompe et vanne arrêtées jusqu’à disparition "
            "des blocages."
        )

    elif active_cooling is True:
        decision = "CONTINUE_COOLING"
        decision_class = "ACTIVE"
        recommendations.append(
            "Poursuivre le refroidissement sous surveillance "
            "de la marge de condensation."
        )

    elif normalized_existing in {
        "START",
        "START_COOLING",
        "COOL",
        "COOLING",
        "ON",
    }:
        decision = "START_COOLING"
        decision_class = "ACTION"
        recommendations.append(
            "Le Brain recommande le démarrage du refroidissement."
        )

    elif normalized_existing in {
        "STOP",
        "STOP_COOLING",
        "OFF",
    }:
        decision = "STOP_COOLING"
        decision_class = "ACTION"
        recommendations.append(
            "Le Brain recommande l’arrêt du refroidissement."
        )

    elif (
        indoor_temperature is not None
        and indoor_temperature >= 25.0
        and (
            predicted_outdoor_max is None
            or predicted_outdoor_max >= 28.0
        )
    ):
        decision = "PREPARE_COOLING"
        decision_class = "ANTICIPATION"
        recommendations.append(
            "Préparer une séquence de refroidissement anticipée."
        )

    elif cold_storage is not None and cold_storage >= 70.0:
        decision = "HOLD_COLD_STORAGE"
        decision_class = "STANDBY"
        recommendations.append(
            "Le stockage de froid est suffisant ; maintenir la veille."
        )

    else:
        decision = "STANDBY"
        decision_class = "STANDBY"
        recommendations.append(
            "Aucune action thermique immédiate n’est nécessaire."
        )

    source_quality = sum(
        1
        for result in (
            brain_result,
            forecast_result,
            twin_result,
            prediction_result,
            system_result,
        )
        if result["available"]
    )

    calculated_confidence = round(
        min(
            100.0,
            source_quality * 14.0
            + (
                _c0213_float(twin.get("data_quality_percent"))
                or 0.0
            ) * 0.2
            + (
                _c0213_float(twin.get("confidence_percent"))
                or 0.0
            ) * 0.1,
        ),
        1,
    )

    confidence = (
        existing_confidence
        if existing_confidence is not None
        else calculated_confidence
    )

    if confidence <= 1:
        confidence *= 100

    confidence = round(
        max(0.0, min(100.0, confidence)),
        1,
    )

    if blockers:
        confidence = max(confidence, 90.0)

    warnings: list[dict[str, Any]] = []

    for name, result in (
        ("brain", brain_result),
        ("forecast", forecast_result),
        ("digital_twin", twin_result),
        ("prediction", prediction_result),
        ("system", system_result),
    ):
        if not result["available"]:
            warnings.append(
                {
                    "component": name,
                    "message": (
                        result.get("error", {}).get("message")
                        or "Composant indisponible"
                    ),
                }
            )

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": _C0213_DECISION_ENGINE_VERSION,
        "status": (
            "READY"
            if not warnings
            else "DEGRADED"
        ),
        "read_only": True,
        "hardware_touched": False,
        "decision": {
            "code": decision,
            "class": decision_class,
            "confidence_percent": confidence,
            "source_decision": existing_decision,
            "action_required": decision not in {
                "STANDBY",
                "HOLD_COLD_STORAGE",
            },
        },
        "explanation": {
            "summary": recommendations[0],
            "reasons": reasons,
            "blockers": blockers,
            "recommendations": recommendations,
        },
        "conditions": {
            "start": conditions_to_start,
            "stop": conditions_to_stop,
        },
        "optimal_window": {
            "start_at": start_at,
            "stop_at": stop_at,
            "available": bool(start_at or stop_at),
        },
        "thermal_context": {
            "indoor_temperature_c": indoor_temperature,
            "outdoor_temperature_c": outdoor_temperature,
            "predicted_outdoor_max_c": predicted_outdoor_max,
            "predicted_indoor_temperature_c": predicted_indoor,
            "floor_surface_temperature_c": floor_surface_temperature,
            "supply_temperature_c": supply_temperature,
            "return_temperature_c": return_temperature,
            "flow_l_min": flow_l_min,
            "cold_storage_percent": cold_storage,
            "condensation_margin_c": condensation_margin,
            "condensation_risk": condensation_risk,
            "pump_running": pump_running,
            "valve_open": valve_open,
            "active_cooling": active_cooling,
        },
        "home_assistant": {
            "state": decision,
            "icon": (
                "mdi:snowflake-alert"
                if blockers
                else (
                    "mdi:snowflake"
                    if decision in {
                        "START_COOLING",
                        "CONTINUE_COOLING",
                        "PREPARE_COOLING",
                    }
                    else "mdi:power-sleep"
                )
            ),
            "message": recommendations[0],
            "severity": (
                "critical"
                if blockers
                else (
                    "warning"
                    if decision == "PREPARE_COOLING"
                    else "normal"
                )
            ),
        },
        "source_availability": {
            "brain": brain_result["available"],
            "forecast": forecast_result["available"],
            "digital_twin": twin_result["available"],
            "prediction": prediction_result["available"],
            "system": system_result["available"],
        },
        "warnings": warnings,
    }


@router.get("/brain/decision-engine")
def get_brain_decision_engine() -> dict[str, Any]:
    """
    Synthèse explicable en lecture seule.

    Cette route ne transmet aucune commande au contrôleur.
    """
    return _c0213_build_decision()




# ============================================================================
# C021.4 — HOME ASSISTANT UNIFIED VIEW
# ============================================================================

_C0214_HOME_ASSISTANT_VERSION = "C021.4-HOME-ASSISTANT-VIEW-1.0"


def _c0214_state(value: Any, default: str = "unknown") -> str:
    if value is None:
        return default

    if isinstance(value, bool):
        return "on" if value else "off"

    return str(value)


def _c0214_number(value: Any) -> float | None:
    if value is None or isinstance(value, bool):
        return None

    try:
        number = float(value)
    except (TypeError, ValueError):
        return None

    if number != number:
        return None

    return round(number, 2)


def _c0214_sensor(
    state: Any,
    *,
    name: str,
    unit: str | None = None,
    icon: str | None = None,
    device_class: str | None = None,
    attributes: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "name": name,
        "state": state,
        "attributes": attributes or {},
    }

    if unit is not None:
        payload["unit_of_measurement"] = unit

    if icon is not None:
        payload["icon"] = icon

    if device_class is not None:
        payload["device_class"] = device_class

    return payload


def _c0214_build_home_assistant_view() -> dict[str, Any]:
    decision_result = _c0212_safe_call(
        lambda: _c0213_build_decision(),
        {},
    )

    twin_result = _c0212_safe_call(
        lambda: digital_twin.snapshot(refresh=False),
        {},
    )

    historian_result = _c0212_safe_call(
        lambda: _c0212_collect_history(limit=1),
        {},
    )

    decision_payload = decision_result["data"] or {}
    decision = decision_payload.get("decision") or {}
    explanation = decision_payload.get("explanation") or {}
    thermal = decision_payload.get("thermal_context") or {}
    ha_decision = decision_payload.get("home_assistant") or {}

    twin = twin_result["data"] or {}

    indoor_temperature = _c0214_number(
        thermal.get("indoor_temperature_c")
        if thermal.get("indoor_temperature_c") is not None
        else twin.get("indoor_air_temperature_c")
    )

    outdoor_temperature = _c0214_number(
        thermal.get("outdoor_temperature_c")
        if thermal.get("outdoor_temperature_c") is not None
        else twin.get("outdoor_air_temperature_c")
    )

    floor_surface_temperature = _c0214_number(
        thermal.get("floor_surface_temperature_c")
        if thermal.get("floor_surface_temperature_c") is not None
        else twin.get("floor_surface_temperature_c")
    )

    supply_temperature = _c0214_number(
        thermal.get("supply_temperature_c")
        if thermal.get("supply_temperature_c") is not None
        else twin.get("supply_temperature_c")
    )

    return_temperature = _c0214_number(
        thermal.get("return_temperature_c")
        if thermal.get("return_temperature_c") is not None
        else twin.get("return_temperature_c")
    )

    flow_l_min = _c0214_number(
        thermal.get("flow_l_min")
        if thermal.get("flow_l_min") is not None
        else twin.get("flow_l_min")
    )

    condensation_margin = _c0214_number(
        thermal.get("condensation_margin_c")
        if thermal.get("condensation_margin_c") is not None
        else twin.get("condensation_margin_c")
    )

    confidence = _c0214_number(
        decision.get("confidence_percent")
    )

    cold_storage = _c0214_number(
        thermal.get("cold_storage_percent")
    )

    decision_code = _c0214_state(
        decision.get("code"),
        "UNKNOWN",
    )

    decision_class = _c0214_state(
        decision.get("class"),
        "UNKNOWN",
    )

    summary = _c0214_state(
        explanation.get("summary"),
        "Aucune recommandation disponible",
    )

    blockers = explanation.get("blockers") or []
    warnings = decision_payload.get("warnings") or []

    pump_running = bool(
        thermal.get("pump_running")
    )

    valve_open = bool(
        thermal.get("valve_open")
    )

    active_cooling = bool(
        thermal.get("active_cooling")
    )

    condensation_risk = _c0214_state(
        thermal.get("condensation_risk"),
        "UNKNOWN",
    )

    available_components = sum(
        1
        for result in (
            decision_result,
            twin_result,
            historian_result,
        )
        if result["available"]
    )

    total_components = 3

    system_available = (
        decision_result["available"]
        and twin_result["available"]
    )

    safety_ok = len(blockers) == 0

    sensors = {
        "system_status": _c0214_sensor(
            "READY" if system_available else "DEGRADED",
            name="GeoCooling état système",
            icon="mdi:server",
            attributes={
                "available_components": available_components,
                "total_components": total_components,
                "version": _C0214_HOME_ASSISTANT_VERSION,
            },
        ),
        "brain_decision": _c0214_sensor(
            decision_code,
            name="GeoCooling décision Brain",
            icon=ha_decision.get("icon") or "mdi:brain",
            attributes={
                "class": decision_class,
                "confidence_percent": confidence,
                "message": summary,
                "severity": ha_decision.get("severity"),
                "action_required": decision.get("action_required"),
            },
        ),
        "brain_confidence": _c0214_sensor(
            confidence,
            name="GeoCooling confiance Brain",
            unit="%",
            icon="mdi:gauge",
        ),
        "brain_message": _c0214_sensor(
            summary,
            name="GeoCooling recommandation",
            icon="mdi:message-text",
            attributes={
                "reasons": explanation.get("reasons") or [],
                "recommendations": (
                    explanation.get("recommendations") or []
                ),
            },
        ),
        "indoor_temperature": _c0214_sensor(
            indoor_temperature,
            name="GeoCooling température intérieure",
            unit="°C",
            device_class="temperature",
            icon="mdi:home-thermometer",
        ),
        "outdoor_temperature": _c0214_sensor(
            outdoor_temperature,
            name="GeoCooling température extérieure",
            unit="°C",
            device_class="temperature",
            icon="mdi:thermometer",
        ),
        "floor_surface_temperature": _c0214_sensor(
            floor_surface_temperature,
            name="GeoCooling température de surface",
            unit="°C",
            device_class="temperature",
            icon="mdi:heat-wave",
        ),
        "supply_temperature": _c0214_sensor(
            supply_temperature,
            name="GeoCooling température départ",
            unit="°C",
            device_class="temperature",
            icon="mdi:coolant-temperature",
        ),
        "return_temperature": _c0214_sensor(
            return_temperature,
            name="GeoCooling température retour",
            unit="°C",
            device_class="temperature",
            icon="mdi:coolant-temperature",
        ),
        "flow_rate": _c0214_sensor(
            flow_l_min,
            name="GeoCooling débit hydraulique",
            unit="L/min",
            icon="mdi:waves-arrow-right",
        ),
        "condensation_margin": _c0214_sensor(
            condensation_margin,
            name="GeoCooling marge condensation",
            unit="°C",
            device_class="temperature",
            icon="mdi:water-alert",
            attributes={
                "risk": condensation_risk,
            },
        ),
        "cold_storage": _c0214_sensor(
            cold_storage,
            name="GeoCooling stockage de froid",
            unit="%",
            icon="mdi:snowflake-thermometer",
        ),
    }

    binary_sensors = {
        "available": _c0214_sensor(
            "on" if system_available else "off",
            name="GeoCooling disponible",
            device_class="connectivity",
            icon="mdi:lan-connect",
        ),
        "safety": _c0214_sensor(
            "on" if safety_ok else "off",
            name="GeoCooling sécurité",
            device_class="safety",
            icon=(
                "mdi:shield-check"
                if safety_ok
                else "mdi:shield-alert"
            ),
            attributes={
                "blocker_count": len(blockers),
                "blockers": blockers,
            },
        ),
        "pump": _c0214_sensor(
            "on" if pump_running else "off",
            name="GeoCooling pompe",
            device_class="running",
            icon="mdi:pump",
        ),
        "valve": _c0214_sensor(
            "on" if valve_open else "off",
            name="GeoCooling vanne",
            device_class="opening",
            icon="mdi:valve",
        ),
        "active_cooling": _c0214_sensor(
            "on" if active_cooling else "off",
            name="GeoCooling refroidissement actif",
            device_class="running",
            icon="mdi:snowflake",
        ),
        "action_required": _c0214_sensor(
            (
                "on"
                if bool(decision.get("action_required"))
                else "off"
            ),
            name="GeoCooling action requise",
            device_class="problem",
            icon="mdi:alert-circle",
        ),
        "condensation_risk": _c0214_sensor(
            (
                "on"
                if condensation_risk in {"HIGH", "CRITICAL"}
                else "off"
            ),
            name="GeoCooling risque condensation",
            device_class="problem",
            icon="mdi:water-alert",
            attributes={
                "risk_level": condensation_risk,
                "margin_c": condensation_margin,
            },
        ),
    }

    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "version": _C0214_HOME_ASSISTANT_VERSION,
        "status": "READY" if system_available else "DEGRADED",
        "read_only": True,
        "hardware_touched": False,
        "entity_prefix": "geocooling",
        "refresh_recommendation_seconds": 30,
        "sensors": sensors,
        "binary_sensors": binary_sensors,
        "summary": {
            "decision": decision_code,
            "confidence_percent": confidence,
            "message": summary,
            "safety_ok": safety_ok,
            "blocker_count": len(blockers),
            "warning_count": len(warnings),
            "pump_running": pump_running,
            "valve_open": valve_open,
            "active_cooling": active_cooling,
        },
        "availability": {
            "decision_engine": decision_result["available"],
            "digital_twin": twin_result["available"],
            "historian": historian_result["available"],
        },
    }


@router.get("/home-assistant/dashboard")
def get_home_assistant_dashboard() -> dict[str, Any]:
    """
    Vue stable et simplifiée destinée à Home Assistant.

    Cette route ne transmet aucune commande matérielle.
    """
    return _c0214_build_home_assistant_view()



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


# PATCH C018 — Diagnostic direct des 8 relais Waveshare.
# Ces routes ne sont disponibles que lorsque le contrôleur utilise réellement
# GEOCOOLING_DRIVER=waveshare_modbus. Toute activation exige un pilote armé ;
# les commandes OFF restent toujours autorisées.
def _waveshare_driver() -> WaveshareModbusDriver:
    if getattr(controller, "driver_name", "") != "waveshare_modbus":
        raise HTTPException(
            status_code=409,
            detail="GEOCOOLING_DRIVER=waveshare_modbus est requis.",
        )
    driver = getattr(controller, "driver", None)
    if not isinstance(driver, WaveshareModbusDriver):
        raise HTTPException(status_code=503, detail="Pilote Waveshare indisponible.")
    return driver


@router.get("/relay/status")
def relay_status() -> dict:
    try:
        return _waveshare_driver().status()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/relay/{relay_id}/on")
def relay_on(relay_id: int) -> dict:
    try:
        driver = _waveshare_driver()
        driver.set_relay(relay_id, True)
        return driver.status()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except RuntimeError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/relay/{relay_id}/off")
def relay_off(relay_id: int) -> dict:
    try:
        driver = _waveshare_driver()
        driver.set_relay(relay_id, False)
        return driver.status()
    except HTTPException:
        raise
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc


@router.post("/relay/all/off")
def relay_all_off() -> dict:
    try:
        driver = _waveshare_driver()
        driver.all_off()
        return driver.status()
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=503, detail=str(exc)) from exc

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


# MACRO SPRINT H007-H010 — commissioning, safety, Brain V3 and field readiness
@router.get("/industrial-platform/safety")
def get_industrial_platform_safety():
    return industrial_platform.safety.evaluate(controller.thermal_status())

@router.post("/industrial-platform/safety/emergency-stop")
def post_industrial_platform_emergency_stop(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.safety.emergency_stop(
            str(payload.get("reason", "")), str(payload.get("operator", "operator"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.post("/industrial-platform/safety/emergency-stop/clear")
def post_industrial_platform_emergency_stop_clear(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    return industrial_platform.safety.clear_emergency_stop(str(payload.get("operator", "operator")))

@router.get("/industrial-platform/brain-v3")
def get_industrial_platform_brain_v3():
    thermal = controller.thermal_status()
    safety = industrial_platform.safety.evaluate(thermal)
    return industrial_platform.brain_v3.analyze(controller.brain_status(), thermal, safety)

@router.get("/industrial-platform/brain-v4")
def get_industrial_platform_brain_v4():
    thermal = controller.thermal_status()
    safety = industrial_platform.safety.evaluate(thermal)
    return industrial_platform.brain_v4.analyze(thermal, safety)

@router.get("/industrial-platform/brain-v4/model")
def get_industrial_platform_brain_v4_model():
    return industrial_platform.brain_v4.model_status()

@router.post("/industrial-platform/brain-v4/weather")
def post_industrial_platform_brain_v4_weather(payload: dict[str, Any] = Body(...)):
    return industrial_platform.brain_v4.update_weather(payload)

@router.post("/industrial-platform/brain-v4/observe")
def post_industrial_platform_brain_v4_observe(payload: dict[str, Any] = Body(...)):
    previous = payload.get("previous") or {}
    current = payload.get("current") or {}
    return industrial_platform.brain_v4.observe(previous, current)


# SPRINT H011 — normalized telemetry and advisory hydraulic planning
@router.post("/industrial-platform/telemetry")
def post_industrial_platform_telemetry(payload: dict[str, Any] = Body(...)):
    return industrial_platform.telemetry.ingest(payload)

@router.get("/industrial-platform/telemetry")
def get_industrial_platform_telemetry():
    return industrial_platform.telemetry.status()

@router.get("/industrial-platform/data-quality")
def get_industrial_platform_data_quality():
    telemetry = industrial_platform.telemetry.status()
    return industrial_platform.data_quality.assess(telemetry.get("latest"), telemetry.get("previous"))

@router.post("/industrial-platform/data-quality/calibration")
def post_industrial_platform_data_quality_calibration(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.data_quality.set_calibration(
            str(payload.get("sensor", "")),
            offset=payload.get("offset"),
            operator=str(payload.get("operator", "operator")),
            note=str(payload.get("note", "")),
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/industrial-platform/operational-plan")
def get_industrial_platform_operational_plan():
    thermal = controller.thermal_status()
    safety = industrial_platform.safety.evaluate(thermal)
    brain = industrial_platform.brain_v4.analyze(thermal, safety)
    return industrial_platform.operational_advisor.build_plan(
        brain=brain, safety=safety, hardware=industrial_platform.hardware.status()
    )


@router.get("/industrial-platform/operational-confidence")
def get_industrial_platform_operational_confidence():
    telemetry = industrial_platform.telemetry.status()
    quality = industrial_platform.data_quality.assess(telemetry.get("latest"), telemetry.get("previous"))
    hardware = industrial_platform.hardware.status()
    return industrial_platform.operational_confidence.evaluate(
        latest=telemetry.get("latest"),
        previous=telemetry.get("previous"),
        quality=quality,
        physical_mode=not bool(hardware.get("simulation", True)),
    )


@router.get("/industrial-platform/commissioning")
def get_industrial_platform_commissioning():
    return industrial_platform.commissioning.status()

@router.post("/industrial-platform/commissioning/start")
def post_industrial_platform_commissioning_start(payload: dict[str, Any] | None = Body(default=None)):
    payload = payload or {}
    return industrial_platform.commissioning.start(str(payload.get("operator", "operator")))

@router.post("/industrial-platform/commissioning/advance")
def post_industrial_platform_commissioning_advance(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.commissioning.advance(str(payload.get("session_id", "")))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.post("/industrial-platform/commissioning/cancel")
def post_industrial_platform_commissioning_cancel(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.commissioning.cancel(
            str(payload.get("session_id", "")), str(payload.get("reason", "operator cancellation"))
        )
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/industrial-platform/field-readiness")
def get_industrial_platform_field_readiness():
    certification = industrial_platform.certification()
    safety = industrial_platform.safety.evaluate(controller.thermal_status())
    commissioning = industrial_platform.commissioning.status()
    software_ready = (
        certification.get("status") == "PASS"
        and safety.get("safe") is True
        and commissioning.get("status") == "SOFTWARE_COMPLETE_HARDWARE_PENDING"
    )
    return {
        "generated_at": utc_now_iso(),
        "version": "H010-FIELD-READINESS-1.0",
        "software_ready": software_ready,
        "physical_activation_allowed": False,
        "hardware_remains_disarmed": True,
        "blocking_items": [
            item for item, blocked in (
                ("pre-certification", certification.get("status") != "PASS"),
                ("safety", safety.get("safe") is not True),
                ("software-commissioning", commissioning.get("status") != "SOFTWARE_COMPLETE_HARDWARE_PENDING"),
                ("physical-waveshare-test", True),
                ("operator-field-authorization", True),
            ) if blocked
        ],
        "pre_certification": certification,
        "safety": safety,
        "commissioning": commissioning,
    }

# SPRINT H014 — persistent anomaly detection and operational availability
@router.get("/industrial-platform/operational-availability")
def get_industrial_platform_operational_availability():
    telemetry = industrial_platform.telemetry.status()
    quality = industrial_platform.data_quality.assess(telemetry.get("latest"), telemetry.get("previous"))
    hardware = industrial_platform.hardware.status()
    safety = industrial_platform.safety.evaluate(controller.thermal_status())
    confidence = industrial_platform.operational_confidence.evaluate(
        latest=telemetry.get("latest"),
        previous=telemetry.get("previous"),
        quality=quality,
        physical_mode=not bool(hardware.get("simulation", True)),
    )
    return industrial_platform.operational_availability.evaluate(
        confidence=confidence,
        quality=quality,
        safety=safety,
        hardware=hardware,
    )


@router.get("/industrial-platform/operational-availability/history")
def get_industrial_platform_operational_availability_history(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.operational_availability.history(limit)

# SPRINT H015 — restart continuity and persisted-state integrity
@router.get("/industrial-platform/operational-continuity")
def get_industrial_platform_operational_continuity():
    telemetry = industrial_platform.telemetry.status()
    quality = industrial_platform.data_quality.assess(telemetry.get("latest"), telemetry.get("previous"))
    hardware = industrial_platform.hardware.status()
    safety = industrial_platform.safety.evaluate(controller.thermal_status())
    confidence = industrial_platform.operational_confidence.evaluate(
        latest=telemetry.get("latest"),
        previous=telemetry.get("previous"),
        quality=quality,
        physical_mode=not bool(hardware.get("simulation", True)),
    )
    availability = industrial_platform.operational_availability.evaluate(
        confidence=confidence,
        quality=quality,
        safety=safety,
        hardware=hardware,
    )
    return industrial_platform.operational_continuity.evaluate(
        availability=availability,
        confidence=confidence,
        safety=safety,
        hardware=hardware,
    )


@router.get("/industrial-platform/operational-continuity/history")
def get_industrial_platform_operational_continuity_history(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.operational_continuity.history(limit)

# SPRINT H016 — global operational orchestration and maintenance mode

def _industrial_operational_context():
    telemetry = industrial_platform.telemetry.status()
    quality = industrial_platform.data_quality.assess(telemetry.get("latest"), telemetry.get("previous"))
    hardware = industrial_platform.hardware.status()
    safety = industrial_platform.safety.evaluate(controller.thermal_status())
    confidence = industrial_platform.operational_confidence.evaluate(
        latest=telemetry.get("latest"),
        previous=telemetry.get("previous"),
        quality=quality,
        physical_mode=not bool(hardware.get("simulation", True)),
    )
    availability = industrial_platform.operational_availability.evaluate(
        confidence=confidence,
        quality=quality,
        safety=safety,
        hardware=hardware,
    )
    continuity = industrial_platform.operational_continuity.evaluate(
        availability=availability,
        confidence=confidence,
        safety=safety,
        hardware=hardware,
    )
    return continuity, availability, confidence, safety, hardware


@router.get("/industrial-platform/operational-orchestration")
def get_industrial_platform_operational_orchestration():
    continuity, availability, confidence, safety, hardware = _industrial_operational_context()
    return industrial_platform.operational_orchestrator.evaluate(
        continuity=continuity,
        availability=availability,
        confidence=confidence,
        safety=safety,
        hardware=hardware,
    )


@router.get("/industrial-platform/operational-orchestration/history")
def get_industrial_platform_operational_orchestration_history(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.operational_orchestrator.history(limit)


@router.post("/industrial-platform/operational-orchestration/maintenance")
def post_industrial_platform_operational_maintenance(payload: dict[str, Any] = Body(...)):
    return industrial_platform.operational_orchestrator.set_maintenance(
        bool(payload.get("active", True)),
        operator=str(payload.get("operator", "unknown")),
        reason=str(payload.get("reason", "maintenance operation")),
    )

# SPRINT H017 — physical thermal model and condensation-safe optimization
@router.get("/industrial-platform/physical-thermal-model")
def get_industrial_platform_physical_thermal_model():
    return industrial_platform.physical_thermal_model.status()


@router.post("/industrial-platform/physical-thermal-model/predict")
def post_industrial_platform_physical_thermal_predict(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.physical_thermal_model.predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/industrial-platform/physical-thermal-model/optimize")
def post_industrial_platform_physical_thermal_optimize(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.physical_thermal_model.optimize(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# SPRINT H018 — bounded thermal model learning
@router.get("/industrial-platform/thermal-model-learning")
def get_industrial_platform_thermal_model_learning():
    return industrial_platform.thermal_model_learning.status()


@router.post("/industrial-platform/thermal-model-learning/observe")
def post_industrial_platform_thermal_model_observe(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.thermal_model_learning.observe(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/industrial-platform/thermal-model-learning/predict")
def post_industrial_platform_thermal_model_learning_predict(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.thermal_model_learning.predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/industrial-platform/thermal-model-learning/reset")
def post_industrial_platform_thermal_model_learning_reset():
    return industrial_platform.thermal_model_learning.reset()

# SPRINT H019 — cross-validation and controlled model promotion
@router.get("/industrial-platform/thermal-model-validation")
def get_industrial_platform_thermal_model_validation():
    return industrial_platform.thermal_model_validation.status()


@router.post("/industrial-platform/thermal-model-validation/evaluate")
def post_industrial_platform_thermal_model_validation_evaluate(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.thermal_model_validation.evaluate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/industrial-platform/thermal-model-validation/promote")
def post_industrial_platform_thermal_model_validation_promote():
    try:
        return industrial_platform.thermal_model_validation.promote()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/industrial-platform/thermal-model-validation/rollback")
def post_industrial_platform_thermal_model_validation_rollback():
    try:
        return industrial_platform.thermal_model_validation.rollback()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc


@router.post("/industrial-platform/thermal-model-validation/predict")
def post_industrial_platform_thermal_model_validation_predict(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.thermal_model_validation.predict(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# SPRINT H020 — 24 h energy optimization and daily assessment
@router.get("/industrial-platform/energy-optimizer")
def get_industrial_platform_energy_optimizer():
    return industrial_platform.energy_optimizer.status()


@router.post("/industrial-platform/energy-optimizer/optimize")
def post_industrial_platform_energy_optimize(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.energy_optimizer.optimize(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.post("/industrial-platform/energy-optimizer/assess")
def post_industrial_platform_energy_assess(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.energy_optimizer.assess(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


@router.get("/industrial-platform/energy-optimizer/assessments")
def get_industrial_platform_energy_assessments(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.energy_optimizer.assessments(limit)


# SPRINT H021 — Explainable Brain V5
@router.get("/industrial-platform/brain-v5")
def get_industrial_platform_brain_v5():
    return industrial_platform.brain_v5.status()


@router.post("/industrial-platform/brain-v5/decide")
def post_industrial_platform_brain_v5_decide(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.brain_v5.decide(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc


# SPRINT H022 — Advisory mission supervision
@router.get("/industrial-platform/mission-supervisor")
def get_industrial_platform_mission_supervisor():
    return industrial_platform.mission_supervisor.status()

@router.post("/industrial-platform/mission-supervisor/start")
def post_industrial_platform_mission_start(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.mission_supervisor.start(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.post("/industrial-platform/mission-supervisor/update")
def post_industrial_platform_mission_update(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.mission_supervisor.update(payload)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.post("/industrial-platform/mission-supervisor/stop")
def post_industrial_platform_mission_stop(payload: dict[str, Any] = Body(default={})):
    try:
        return industrial_platform.mission_supervisor.stop(str(payload.get("reason") or "OPERATOR_STOP"))
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc

@router.get("/industrial-platform/mission-supervisor/history")
def get_industrial_platform_mission_history(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.mission_supervisor.missions(limit)



# SPRINT H023 — Hardware readiness without physical activation
@router.get("/industrial-platform/hardware-readiness")
def get_industrial_platform_hardware_readiness():
    return industrial_platform.hardware_readiness.status()

@router.post("/industrial-platform/hardware-readiness/dry-run")
def post_industrial_platform_hardware_readiness_dry_run():
    return industrial_platform.hardware_readiness.dry_run_sequence()


# SPRINT H024 — Non-invasive field wiring certification
@router.get("/industrial-platform/field-certification")
def get_industrial_platform_field_certification():
    return industrial_platform.field_certification.status()

@router.post("/industrial-platform/field-certification/evaluate")
def post_industrial_platform_field_certification(payload: dict[str, Any] = Body(...)):
    try:
        return industrial_platform.field_certification.evaluate(payload)
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

@router.get("/industrial-platform/field-certification/history")
def get_industrial_platform_field_certification_history(limit: int = Query(default=20, ge=1, le=100)):
    return industrial_platform.field_certification.certificates(limit)


@router.get("/geocooling/industrial-platform/digital-twin")
def get_geocooling_industrial_platform_digital_twin():
    return industrial_platform.digital_twin.status()

from pydantic import BaseModel


class BrainSimulationRequest(BaseModel):
    indoor_temperature_c: float
    indoor_humidity_percent: float

    outdoor_temperature_c: float | None = None

    source_inlet_temperature_c: float | None = None

    source_outlet_temperature_c: float | None = None

    supply_temperature_c: float | None = None

    return_temperature_c: float | None = None

    flow_rate_l_min: float | None = None

    pump_running: bool = False

    valve_open: bool = False


@router.post(
    "/geocooling/simulation/evaluate",
    tags=["GeoCooling"],
)
def evaluate_simulation(
    payload: BrainSimulationRequest,
):
    latest = payload.model_dump()

    thermal = {
        "latest": latest,
    }

    safety = {
        "safe": True,
    }

    device = {
        "ready": True,
    }

    decision = controller.brain._c0123r4_original_evaluate(
        state=controller.state.value,
        thermal=thermal,
        safety=safety,
        device=device,
    )

    return decision.as_dict()

