from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timedelta, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    """Retourne une date UTC avec fuseau horaire."""
    return datetime.now(timezone.utc)


class GeoCoolingState(StrEnum):
    OFF = "OFF"
    OPENING_VALVE = "OPENING_VALVE"
    WAITING_FLOW = "WAITING_FLOW"
    STARTING_PUMP = "STARTING_PUMP"
    RUNNING = "RUNNING"
    STOPPING_PUMP = "STOPPING_PUMP"
    WAITING_DRAIN = "WAITING_DRAIN"
    CLOSING_VALVE = "CLOSING_VALVE"
    FAULT = "FAULT"
    EMERGENCY_STOP = "EMERGENCY_STOP"


class GeoCoolingMode(StrEnum):
    # Modes historiques conservés sans modification.
    SIMULATION = "SIMULATION"
    MANUAL = "MANUAL"
    AUTO = "AUTO"
    OFF = "OFF"

    # Nouveau mode introduit progressivement par la version 0.7.0.
    MANUAL_SAFE = "MANUAL_SAFE"


class ManualCommandType(StrEnum):
    START = "START"
    STOP = "STOP"
    CANCEL = "CANCEL"


class ManualCommandStatus(StrEnum):
    PENDING = "PENDING"
    ACCEPTED = "ACCEPTED"
    REFUSED = "REFUSED"
    FINISHED = "FINISHED"
    EXPIRED = "EXPIRED"
    CANCELLED = "CANCELLED"


@dataclass(slots=True)
class ManualCommand:
    """
    Demande manuelle destinée au contrôleur GeoCooling.

    Cette structure ne pilote aucun relais directement.
    La commande devra être validée par le CommandManager
    et par les sécurités du contrôleur.
    """

    command: ManualCommandType
    requested_by: str

    duration_seconds: int = 900
    reason: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)

    id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)

    status: ManualCommandStatus = ManualCommandStatus.PENDING
    finished_at: datetime | None = None
    refusal_reason: str | None = None

    def __post_init__(self) -> None:
        self.requested_by = self.requested_by.strip() or "unknown"
        self.reason = self.reason.strip()

        if self.duration_seconds < 1:
            raise ValueError(
                "duration_seconds doit être supérieur ou égal à 1"
            )

        if self.created_at.tzinfo is None:
            self.created_at = self.created_at.replace(
                tzinfo=timezone.utc
            )

    @property
    def expires_at(self) -> datetime:
        return self.created_at + timedelta(
            seconds=self.duration_seconds
        )

    @property
    def expired(self) -> bool:
        return utc_now() >= self.expires_at

    @property
    def terminal(self) -> bool:
        return self.status in {
            ManualCommandStatus.REFUSED,
            ManualCommandStatus.FINISHED,
            ManualCommandStatus.EXPIRED,
            ManualCommandStatus.CANCELLED,
        }

    def accept(self) -> None:
        if self.terminal:
            raise RuntimeError(
                "Une commande terminée ne peut pas être acceptée"
            )

        self.status = ManualCommandStatus.ACCEPTED
        self.refusal_reason = None

    def refuse(self, reason: str) -> None:
        if self.terminal:
            raise RuntimeError(
                "Une commande terminée ne peut pas être refusée"
            )

        refusal_reason = reason.strip()

        if not refusal_reason:
            raise ValueError(
                "Une raison de refus est obligatoire"
            )

        self.status = ManualCommandStatus.REFUSED
        self.refusal_reason = refusal_reason
        self.finished_at = utc_now()

    def cancel(self) -> None:
        if self.terminal:
            return

        self.status = ManualCommandStatus.CANCELLED
        self.finished_at = utc_now()

    def finish(self) -> None:
        if self.terminal:
            return

        self.status = ManualCommandStatus.FINISHED
        self.finished_at = utc_now()

    def expire(self) -> None:
        if self.terminal:
            return

        self.status = ManualCommandStatus.EXPIRED
        self.finished_at = utc_now()

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "command": self.command.value,
            "requested_by": self.requested_by,
            "status": self.status.value,
            "created_at": self.created_at.isoformat(),
            "expires_at": self.expires_at.isoformat(),
            "finished_at": (
                self.finished_at.isoformat()
                if self.finished_at
                else None
            ),
            "duration_seconds": self.duration_seconds,
            "reason": self.reason,
            "metadata": dict(self.metadata),
            "refusal_reason": self.refusal_reason,
            "expired": self.expired,
            "terminal": self.terminal,
        }
