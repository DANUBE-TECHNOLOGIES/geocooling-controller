from __future__ import annotations

from dataclasses import dataclass
from threading import Lock
from typing import Final


OPERATING_MODE_RANK: Final[dict[str, int]] = {
    "INSUFFICIENT_DATA": 0,
    "LIMITED": 1,
    "BUILDING_ONLY": 2,
    "FULL": 3,
}


@dataclass(frozen=True, slots=True)
class OperatingModeTransition:
    previous_mode: str | None
    observed_mode: str
    effective_mode: str
    changed: bool
    pending_cycles: int
    required_cycles: int
    reason: str


class OperatingModeTracker:
    """Stabilise les changements de capacité entre deux évaluations du Brain.

    Le premier mode observé devient immédiatement effectif. Ensuite, une
    dégradation ou une restauration doit être confirmée pendant plusieurs
    cycles consécutifs. Une observation du mode effectif annule toute transition
    en attente.
    """

    def __init__(
        self,
        *,
        degradation_cycles: int = 2,
        recovery_cycles: int = 3,
    ) -> None:
        self.degradation_cycles = max(1, int(degradation_cycles))
        self.recovery_cycles = max(1, int(recovery_cycles))
        self._effective_mode: str | None = None
        self._candidate_mode: str | None = None
        self._candidate_cycles = 0
        self._lock = Lock()

    @staticmethod
    def _validate(mode: str) -> str:
        if mode not in OPERATING_MODE_RANK:
            raise ValueError(f"Mode de fonctionnement inconnu : {mode}")
        return mode

    def observe(self, observed_mode: str) -> OperatingModeTransition:
        observed_mode = self._validate(observed_mode)

        with self._lock:
            if self._effective_mode is None:
                self._effective_mode = observed_mode
                return OperatingModeTransition(
                    previous_mode=None,
                    observed_mode=observed_mode,
                    effective_mode=observed_mode,
                    changed=True,
                    pending_cycles=0,
                    required_cycles=1,
                    reason="Initialisation du mode de capacité",
                )

            previous_mode = self._effective_mode

            if observed_mode == self._effective_mode:
                pending_was_active = self._candidate_mode is not None
                self._candidate_mode = None
                self._candidate_cycles = 0
                return OperatingModeTransition(
                    previous_mode=previous_mode,
                    observed_mode=observed_mode,
                    effective_mode=self._effective_mode,
                    changed=False,
                    pending_cycles=0,
                    required_cycles=0,
                    reason=(
                        "Transition en attente annulée : capacités stabilisées"
                        if pending_was_active
                        else "Mode de capacité stable"
                    ),
                )

            if observed_mode != self._candidate_mode:
                self._candidate_mode = observed_mode
                self._candidate_cycles = 1
            else:
                self._candidate_cycles += 1

            degrading = (
                OPERATING_MODE_RANK[observed_mode]
                < OPERATING_MODE_RANK[self._effective_mode]
            )
            required_cycles = (
                self.degradation_cycles
                if degrading
                else self.recovery_cycles
            )

            if self._candidate_cycles >= required_cycles:
                self._effective_mode = observed_mode
                self._candidate_mode = None
                self._candidate_cycles = 0
                return OperatingModeTransition(
                    previous_mode=previous_mode,
                    observed_mode=observed_mode,
                    effective_mode=observed_mode,
                    changed=True,
                    pending_cycles=0,
                    required_cycles=required_cycles,
                    reason=(
                        "Dégradation des capacités confirmée"
                        if degrading
                        else "Restauration des capacités confirmée"
                    ),
                )

            return OperatingModeTransition(
                previous_mode=previous_mode,
                observed_mode=observed_mode,
                effective_mode=self._effective_mode,
                changed=False,
                pending_cycles=self._candidate_cycles,
                required_cycles=required_cycles,
                reason=(
                    "Dégradation des capacités en attente de confirmation"
                    if degrading
                    else "Restauration des capacités en attente de confirmation"
                ),
            )

    def reset(self) -> None:
        with self._lock:
            self._effective_mode = None
            self._candidate_mode = None
            self._candidate_cycles = 0
