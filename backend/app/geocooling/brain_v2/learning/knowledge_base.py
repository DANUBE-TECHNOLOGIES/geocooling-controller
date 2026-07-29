from __future__ import annotations

from copy import deepcopy
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.geocooling.brain_v2.learning.persistence import (
    AtomicJSONFile,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class BrainV2KnowledgeBase:
    VERSION = "C022.1-KNOWLEDGE-BASE-1.0"

    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.data_directory.mkdir(parents=True, exist_ok=True)

        self.storage = AtomicJSONFile(
            self.data_directory / "knowledge.json"
        )

        if not self.storage.path.exists():
            self.storage.write(self._initial_state())

    def _initial_state(self) -> dict[str, Any]:
        now = utc_now_iso()

        return {
            "version": self.VERSION,
            "created_at": now,
            "updated_at": now,
            "revision": 1,
            "learning_state": "COLLECTING",
            "models": {
                "building": {
                    "status": "NOT_TRAINED",
                    "sample_count": 0,
                    "parameters": {},
                },
                "floor": {
                    "status": "NOT_TRAINED",
                    "sample_count": 0,
                    "parameters": {},
                },
                "hydraulic": {
                    "status": "NOT_TRAINED",
                    "sample_count": 0,
                    "parameters": {},
                },
                "energy": {
                    "status": "NOT_TRAINED",
                    "sample_count": 0,
                    "parameters": {},
                },
                "weather": {
                    "status": "NOT_TRAINED",
                    "sample_count": 0,
                    "parameters": {},
                },
            },
            "statistics": {
                "accepted_observations": 0,
                "rejected_observations": 0,
                "first_observation_at": None,
                "last_observation_at": None,
            },
            "calibration": {
                "status": "NOT_STARTED",
                "last_run_at": None,
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return deepcopy(
            self.storage.read(self._initial_state())
        )

    def register_observation(
        self,
        observation: dict[str, Any],
    ) -> dict[str, Any]:
        state = self.snapshot()
        statistics = state.setdefault("statistics", {})

        accepted = int(
            statistics.get("accepted_observations", 0)
        ) + 1

        statistics["accepted_observations"] = accepted
        statistics["last_observation_at"] = observation.get(
            "observed_at"
        )

        if not statistics.get("first_observation_at"):
            statistics["first_observation_at"] = (
                observation.get("observed_at")
            )

        state["updated_at"] = utc_now_iso()
        state["revision"] = int(state.get("revision", 0)) + 1

        if accepted >= 288:
            state["learning_state"] = "READY_FOR_TRAINING"
        elif accepted >= 24:
            state["learning_state"] = "BASELINE_COLLECTION"
        else:
            state["learning_state"] = "COLLECTING"

        self.storage.write(state)
        return deepcopy(state)

    def register_rejection(self) -> dict[str, Any]:
        state = self.snapshot()
        statistics = state.setdefault("statistics", {})

        statistics["rejected_observations"] = int(
            statistics.get("rejected_observations", 0)
        ) + 1

        state["updated_at"] = utc_now_iso()
        state["revision"] = int(state.get("revision", 0)) + 1

        self.storage.write(state)
        return deepcopy(state)

    def status(self) -> dict[str, Any]:
        state = self.snapshot()

        return {
            "version": state.get("version"),
            "revision": state.get("revision"),
            "learning_state": state.get("learning_state"),
            "created_at": state.get("created_at"),
            "updated_at": state.get("updated_at"),
            "statistics": state.get("statistics") or {},
            "model_count": len(state.get("models") or {}),
            "path": str(self.storage.path),
        }
