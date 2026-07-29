from __future__ import annotations

import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.geocooling.brain_v2.learning.knowledge_base import (
    BrainV2KnowledgeBase,
)
from app.geocooling.brain_v2.learning.observation_store import (
    BrainV2ObservationStore,
)
from app.geocooling.brain_v2.models.observation import (
    BrainV2Observation,
    ObservationValidationError,
)


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingBrainV2:
    VERSION = "C022.1-BRAIN-V2-FOUNDATION-1.0"

    def __init__(
        self,
        data_directory: str | Path | None = None,
    ) -> None:
        configured_path = (
            data_directory
            or os.getenv("GEOCOOLING_BRAIN_V2_DATA_DIR")
            or "/app/data/geocooling/brain_v2"
        )

        self.data_directory = Path(configured_path)
        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.observations = BrainV2ObservationStore(
            self.data_directory
        )

        self.knowledge = BrainV2KnowledgeBase(
            self.data_directory
        )

        self._lock = threading.RLock()

    def observe(
        self,
        payload: dict[str, Any],
        *,
        source: str = "api",
    ) -> dict[str, Any]:
        with self._lock:
            try:
                observation = BrainV2Observation.from_payload(
                    payload,
                    source=source,
                )
            except ObservationValidationError:
                self.knowledge.register_rejection()
                raise

            stored = self.observations.append(observation)
            knowledge = self.knowledge.register_observation(stored)

            return {
                "accepted": True,
                "observation": stored,
                "learning_state": knowledge.get(
                    "learning_state"
                ),
                "observation_count": (
                    knowledge.get("statistics", {}).get(
                        "accepted_observations",
                        0,
                    )
                ),
            }

    def status(self) -> dict[str, Any]:
        observation_status = self.observations.status()
        knowledge_status = self.knowledge.status()

        writable = os.access(
            self.data_directory,
            os.W_OK,
        )

        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": "READY" if writable else "DEGRADED",
            "enabled": True,
            "learning_enabled": True,
            "decision_authority": False,
            "hardware_control": False,
            "read_only_hardware": True,
            "data_directory": str(self.data_directory),
            "data_directory_writable": writable,
            "observation_store": observation_status,
            "knowledge_base": knowledge_status,
            "capabilities": {
                "observation_ingestion": True,
                "persistent_memory": True,
                "knowledge_base": True,
                "building_learning": False,
                "floor_learning": False,
                "hydraulic_learning": False,
                "energy_learning": False,
                "multi_hour_prediction": False,
                "automatic_optimization": False,
            },
        }

    def snapshot(self) -> dict[str, Any]:
        return {
            "generated_at": utc_now_iso(),
            "version": self.VERSION,
            "status": self.status(),
            "latest_observation": self.observations.latest(),
            "knowledge": self.knowledge.snapshot(),
        }

    def recent_observations(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        return self.observations.recent(limit=limit)
