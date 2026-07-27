from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


@dataclass(frozen=True)
class TimingDecision:
    allowed: bool
    reason: str
    remaining_seconds: int = 0

    def as_dict(self) -> dict[str, Any]:
        return {
            "allowed": self.allowed,
            "reason": self.reason,
            "remaining_seconds": self.remaining_seconds,
        }


class RuntimeGuards:
    """Temporisations de protection du circulateur et de l'électrovanne."""

    def __init__(self, *, minimum_on_seconds: int, minimum_off_seconds: int) -> None:
        self.minimum_on_seconds = max(0, int(minimum_on_seconds))
        self.minimum_off_seconds = max(0, int(minimum_off_seconds))

    @staticmethod
    def _elapsed_seconds(since: datetime | None, now: datetime | None = None) -> int | None:
        if since is None:
            return None
        reference = now or utc_now()
        return max(0, int((reference - since).total_seconds()))

    def can_start(self, *, stopped_at: datetime | None, now: datetime | None = None) -> TimingDecision:
        elapsed = self._elapsed_seconds(stopped_at, now)
        if elapsed is None or elapsed >= self.minimum_off_seconds:
            return TimingDecision(True, "Temporisation minimale d'arrêt respectée")
        remaining = self.minimum_off_seconds - elapsed
        return TimingDecision(False, "Anti-court-cycle actif", remaining)

    def can_stop(self, *, started_at: datetime | None, now: datetime | None = None) -> TimingDecision:
        elapsed = self._elapsed_seconds(started_at, now)
        if elapsed is None or elapsed >= self.minimum_on_seconds:
            return TimingDecision(True, "Durée minimale de marche respectée")
        remaining = self.minimum_on_seconds - elapsed
        return TimingDecision(False, "Durée minimale de marche active", remaining)
