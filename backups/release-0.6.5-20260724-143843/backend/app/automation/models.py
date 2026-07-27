from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class AutomationState(StrEnum):
    PENDING = "pending"
    VALIDATING = "validating"
    APPROVED = "approved"
    EXECUTING = "executing"
    SUCCESS = "success"
    FAILED = "failed"
    REJECTED = "rejected"
    CANCELLED = "cancelled"


class AutomationMode(StrEnum):
    SIMULATION = "simulation"
    REAL = "real"


class AutomationAction(StrEnum):
    START = "start"
    STOP = "stop"
    PRECOOL = "precool"
    EMERGENCY_STOP = "emergency_stop"


TERMINAL_STATES = {
    AutomationState.SUCCESS,
    AutomationState.FAILED,
    AutomationState.REJECTED,
    AutomationState.CANCELLED,
}


@dataclass(slots=True)
class AutomationExecution:
    subsystem: str
    action: AutomationAction
    mode: AutomationMode
    requested_by: str = "api"
    duration_minutes: int | None = None
    reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)
    execution_id: str = field(default_factory=lambda: str(uuid4()))
    state: AutomationState = AutomationState.PENDING
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)
    started_at: datetime | None = None
    completed_at: datetime | None = None
    message: str | None = None
    error: str | None = None
    result: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        data = asdict(self)
        data["action"] = self.action.value
        data["mode"] = self.mode.value
        data["state"] = self.state.value
        for key in ("created_at", "updated_at", "started_at", "completed_at"):
            value = data[key]
            data[key] = value.isoformat() if value else None
        return data
