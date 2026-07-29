from __future__ import annotations

import json
import os
import threading
from pathlib import Path
from typing import Any, Iterable

from app.geocooling.brain_v2.models.observation import (
    BrainV2Observation,
)


class BrainV2ObservationStore:
    def __init__(self, data_directory: Path) -> None:
        self.data_directory = data_directory
        self.data_directory.mkdir(parents=True, exist_ok=True)

        self.path = (
            self.data_directory
            / "observations.jsonl"
        )

        self._lock = threading.RLock()

    def append(
        self,
        observation: BrainV2Observation,
    ) -> dict[str, Any]:
        payload = observation.to_dict()

        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            default=str,
        )

        with self._lock:
            with self.path.open(
                "a",
                encoding="utf-8",
            ) as output:
                output.write(serialized)
                output.write("\n")
                output.flush()
                os.fsync(output.fileno())

        return payload

    def _iter_valid_records(
        self,
    ) -> Iterable[dict[str, Any]]:
        if not self.path.exists():
            return []

        records: list[dict[str, Any]] = []

        with self._lock:
            with self.path.open(
                "r",
                encoding="utf-8",
            ) as source:
                for line in source:
                    line = line.strip()

                    if not line:
                        continue

                    try:
                        payload = json.loads(line)
                    except json.JSONDecodeError:
                        continue

                    if isinstance(payload, dict):
                        records.append(payload)

        return records

    def recent(
        self,
        limit: int = 100,
    ) -> list[dict[str, Any]]:
        records = list(self._iter_valid_records())

        return records[-limit:][::-1]

    def latest(self) -> dict[str, Any] | None:
        records = self.recent(limit=1)
        return records[0] if records else None

    def count(self) -> int:
        return sum(1 for _ in self._iter_valid_records())

    def size_bytes(self) -> int:
        if not self.path.exists():
            return 0

        return self.path.stat().st_size

    def status(self) -> dict[str, Any]:
        return {
            "path": str(self.path),
            "exists": self.path.exists(),
            "observation_count": self.count(),
            "size_bytes": self.size_bytes(),
            "format": "jsonl",
            "append_only": True,
        }
