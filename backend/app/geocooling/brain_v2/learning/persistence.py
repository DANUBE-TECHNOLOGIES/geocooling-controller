from __future__ import annotations

import json
import os
import tempfile
import threading
from pathlib import Path
from typing import Any


class AtomicJSONFile:
    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()

    def read(self, default: Any) -> Any:
        with self._lock:
            if not self.path.exists():
                return default

            try:
                return json.loads(
                    self.path.read_text(encoding="utf-8")
                )
            except (OSError, json.JSONDecodeError):
                return default

    def write(self, payload: Any) -> None:
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            indent=2,
            sort_keys=True,
            default=str,
        )

        with self._lock:
            self.path.parent.mkdir(
                parents=True,
                exist_ok=True,
            )

            file_descriptor, temporary_name = tempfile.mkstemp(
                prefix=f".{self.path.name}.",
                suffix=".tmp",
                dir=str(self.path.parent),
                text=True,
            )

            try:
                with os.fdopen(
                    file_descriptor,
                    "w",
                    encoding="utf-8",
                ) as temporary_file:
                    temporary_file.write(serialized)
                    temporary_file.write("\n")
                    temporary_file.flush()
                    os.fsync(temporary_file.fileno())

                os.replace(temporary_name, self.path)

            finally:
                temporary_path = Path(temporary_name)

                if temporary_path.exists():
                    temporary_path.unlink(missing_ok=True)
