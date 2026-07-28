from __future__ import annotations

import json
import os
import threading
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


class GeoCoolingDecisionJournal:
    """Journal JSONL persistant des décisions du Brain.

    Écriture append-only, lecture tolérante aux lignes invalides et rotation
    simple par taille. Le journal n'exécute aucune commande matérielle.
    """

    def __init__(self, path: str | None = None, max_bytes: int | None = None) -> None:
        self.path = Path(path or os.getenv(
            "GEOCOOLING_BRAIN_JOURNAL_PATH",
            "/var/lib/geocooling/brain-decisions.jsonl",
        ))
        self.max_bytes = max(64 * 1024, int(max_bytes or os.getenv(
            "GEOCOOLING_BRAIN_JOURNAL_MAX_BYTES",
            str(5 * 1024 * 1024),
        )))
        self._lock = threading.RLock()
        self._write_errors = 0
        self._last_error: str | None = None
        self._last_write_at: str | None = None
        self._ensure_parent()

    def _ensure_parent(self) -> None:
        try:
            self.path.parent.mkdir(parents=True, exist_ok=True)
        except OSError as exc:
            self._write_errors += 1
            self._last_error = str(exc)

    def _rotate_if_needed(self, incoming_bytes: int) -> None:
        if not self.path.exists():
            return
        try:
            current = self.path.stat().st_size
        except OSError:
            return
        if current + incoming_bytes <= self.max_bytes:
            return
        rotated = self.path.with_suffix(self.path.suffix + ".1")
        try:
            if rotated.exists():
                rotated.unlink()
            self.path.replace(rotated)
        except OSError as exc:
            self._write_errors += 1
            self._last_error = str(exc)

    def append(self, payload: dict[str, Any]) -> bool:
        line = json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n"
        encoded = line.encode("utf-8")
        with self._lock:
            try:
                self._ensure_parent()
                self._rotate_if_needed(len(encoded))
                with self.path.open("ab") as handle:
                    handle.write(encoded)
                    handle.flush()
                    os.fsync(handle.fileno())
                self._last_write_at = datetime.now(timezone.utc).isoformat()
                self._last_error = None
                return True
            except OSError as exc:
                self._write_errors += 1
                self._last_error = str(exc)
                return False

    @staticmethod
    def _read_file(path: Path) -> list[dict[str, Any]]:
        if not path.exists():
            return []
        items: list[dict[str, Any]] = []
        try:
            with path.open("r", encoding="utf-8", errors="replace") as handle:
                for line in handle:
                    try:
                        value = json.loads(line)
                    except json.JSONDecodeError:
                        continue
                    if isinstance(value, dict):
                        items.append(value)
        except OSError:
            return []
        return items

    def read(self, limit: int = 500) -> list[dict[str, Any]]:
        normalized = max(1, min(int(limit), 5000))
        with self._lock:
            rotated = self.path.with_suffix(self.path.suffix + ".1")
            items = self._read_file(rotated) + self._read_file(self.path)
        return items[-normalized:][::-1]

    def load_recent(self, limit: int = 200) -> list[dict[str, Any]]:
        return list(reversed(self.read(limit)))

    def status(self) -> dict[str, Any]:
        with self._lock:
            exists = self.path.exists()
            size = self.path.stat().st_size if exists else 0
            rotated = self.path.with_suffix(self.path.suffix + ".1")
            rotated_size = rotated.stat().st_size if rotated.exists() else 0
            return {
                "enabled": True,
                "path": str(self.path),
                "exists": exists,
                "size_bytes": size,
                "rotated_size_bytes": rotated_size,
                "max_bytes": self.max_bytes,
                "write_errors": self._write_errors,
                "last_error": self._last_error,
                "last_write_at": self._last_write_at,
            }
