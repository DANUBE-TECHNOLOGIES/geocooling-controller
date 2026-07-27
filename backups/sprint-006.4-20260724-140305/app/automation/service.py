from __future__ import annotations

import logging
import threading
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from app.automation.models import (
    AutomationAction,
    AutomationExecution,
    AutomationMode,
    AutomationState,
    TERMINAL_STATES,
)
from app.automation.repository import AutomationRepository
from app.events.bus import EventBus

logger = logging.getLogger("sbc.automation")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutomationService:
    def __init__(
        self,
        engine: Engine,
        event_bus: EventBus,
        device_manager: Any,
        geocooling_controller: Any,
    ) -> None:
        self.repository = AutomationRepository(engine)
        self.event_bus = event_bus
        self.device_manager = device_manager
        self.geocooling_controller = geocooling_controller
        self._lock = threading.RLock()
        self._executions: dict[str, AutomationExecution] = {}
        self.running = False
        self.started_at: datetime | None = None
        self.last_execution_at: datetime | None = None
        self.last_error: str | None = None
        self.accepted_count = 0
        self.success_count = 0
        self.failed_count = 0
        self.rejected_count = 0
        self.cancelled_count = 0

    def start(self) -> None:
        if self.running:
            return
        self.repository.initialize()
        self.running = True
        self.started_at = utc_now()
        self.event_bus.publish(
            "automation.service_started",
            "automation",
            {"mode": "simulation_ready"},
        )

    def stop(self) -> None:
        self.running = False

    def create(
        self,
        subsystem: str,
        action: AutomationAction,
        mode: AutomationMode,
        requested_by: str = "api",
        duration_minutes: int | None = None,
        reason: str | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> AutomationExecution:
        item = AutomationExecution(
            subsystem=subsystem.strip().lower(),
            action=action,
            mode=mode,
            requested_by=requested_by,
            duration_minutes=duration_minutes,
            reason=reason,
            metadata=metadata or {},
        )
        with self._lock:
            self._executions[item.execution_id] = item
            self.accepted_count += 1
        self._save_and_event(item, "automation.requested")
        threading.Thread(
            target=self._execute,
            args=(item,),
            name=f"automation-{item.execution_id[:8]}",
            daemon=True,
        ).start()
        return item

    def _transition(
        self,
        item: AutomationExecution,
        state: AutomationState,
        message: str,
        event_type: str,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        with self._lock:
            item.state = state
            item.updated_at = utc_now()
            item.message = message
            item.error = error
            if result is not None:
                item.result = result
            if state == AutomationState.EXECUTING and item.started_at is None:
                item.started_at = item.updated_at
            if state in TERMINAL_STATES:
                item.completed_at = item.updated_at
                self.last_execution_at = item.updated_at
        self._save_and_event(item, event_type)

    def _save_and_event(self, item: AutomationExecution, event_type: str) -> None:
        self.repository.save(item)
        self.event_bus.publish(
            event_type,
            "automation",
            {
                "execution_id": item.execution_id,
                "subsystem": item.subsystem,
                "action": item.action.value,
                "mode": item.mode.value,
                "state": item.state.value,
                "message": item.message,
                "error": item.error,
            },
            correlation_id=item.execution_id,
        )

    def _execute(self, item: AutomationExecution) -> None:
        try:
            self._transition(
                item,
                AutomationState.VALIDATING,
                "Validation de la demande",
                "automation.validating",
            )
            rejection = self._validate(item)
            if rejection:
                self.rejected_count += 1
                self._transition(
                    item,
                    AutomationState.REJECTED,
                    rejection,
                    "automation.rejected",
                )
                return

            self._transition(
                item,
                AutomationState.APPROVED,
                "Demande approuvée",
                "automation.approved",
            )
            self._transition(
                item,
                AutomationState.EXECUTING,
                "Exécution en cours",
                "automation.executing",
            )
            result = self._dispatch(item)
            accepted = bool(result.get("accepted", True))
            if not accepted:
                self.failed_count += 1
                self._transition(
                    item,
                    AutomationState.FAILED,
                    result.get("message", "Commande refusée"),
                    "automation.failed",
                    result=result,
                )
                return
            self.success_count += 1
            self._transition(
                item,
                AutomationState.SUCCESS,
                result.get("message", "Exécution terminée"),
                "automation.succeeded",
                result=result,
            )
        except Exception as exc:
            logger.exception("Échec automation %s", item.execution_id)
            self.failed_count += 1
            self.last_error = str(exc)
            self._transition(
                item,
                AutomationState.FAILED,
                "Erreur d'exécution",
                "automation.failed",
                error=str(exc),
            )

    def _validate(self, item: AutomationExecution) -> str | None:
        if item.subsystem != "geocooling":
            return f"Sous-système non supporté : {item.subsystem}"
        if item.mode == AutomationMode.REAL:
            status = self.device_manager.get_device("geocooling-controller")
            if not status:
                return "Équipement geocooling-controller inconnu"
            if status.get("status") not in {"online", "ready"}:
                return "Commande réelle refusée : ESP32 hors ligne"
        return None

    def _dispatch(self, item: AutomationExecution) -> dict[str, Any]:
        if item.action in {AutomationAction.START, AutomationAction.PRECOOL}:
            result = self.geocooling_controller.request_start()
            return {
                **result,
                "simulation": item.mode == AutomationMode.SIMULATION,
                "requested_duration_minutes": item.duration_minutes,
            }
        if item.action == AutomationAction.STOP:
            result = self.geocooling_controller.request_stop()
            if not result.get("accepted") and "déjà arrêté" in result.get("message", ""):
                result = {**result, "accepted": True}
            return result
        if item.action == AutomationAction.EMERGENCY_STOP:
            return self.geocooling_controller.emergency_stop()
        raise ValueError(f"Action non supportée : {item.action.value}")

    def cancel(self, execution_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._executions.get(execution_id)
            if item is None:
                return self.repository.get(execution_id)
            if item.state in TERMINAL_STATES:
                return item.to_dict()
            item.state = AutomationState.CANCELLED
            item.updated_at = utc_now()
            item.completed_at = item.updated_at
            item.message = "Exécution annulée"
            self.cancelled_count += 1
        if item.subsystem == "geocooling":
            self.geocooling_controller.request_stop()
        self._save_and_event(item, "automation.cancelled")
        return item.to_dict()

    def get(self, execution_id: str) -> dict[str, Any] | None:
        with self._lock:
            item = self._executions.get(execution_id)
            if item:
                return item.to_dict()
        return self.repository.get(execution_id)

    def list(self, limit: int = 100, state: str | None = None) -> list[dict[str, Any]]:
        return self.repository.list(limit=limit, state=state)

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            active = sum(1 for item in self._executions.values() if item.state not in TERMINAL_STATES)
        return {
            "running": self.running,
            "started_at": self.started_at,
            "last_execution_at": self.last_execution_at,
            "last_error": self.last_error,
            "active_count": active,
            "accepted_count": self.accepted_count,
            "success_count": self.success_count,
            "failed_count": self.failed_count,
            "rejected_count": self.rejected_count,
            "cancelled_count": self.cancelled_count,
            "supported_subsystems": ["geocooling"],
            "supported_actions": [action.value for action in AutomationAction],
            "real_execution_policy": "ESP32 must be online",
        }
