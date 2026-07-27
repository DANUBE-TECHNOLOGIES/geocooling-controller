"""Construction centralisée du snapshot GeoCooling.

PATCH C011A — Snapshot Builder

Le composant construit une représentation cohérente de l'état courant
du Controller. Il ne pilote aucun relais et ne modifie aucun état.
"""

from __future__ import annotations

import copy
import threading
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingSnapshotBuilder:
    """Façade thread-safe de construction du snapshot Controller."""

    def __init__(self, controller: Any) -> None:
        if controller is None:
            raise ValueError("Un Controller est requis.")

        self.controller = controller
        self._lock = threading.RLock()

        self._build_count = 0
        self._success_count = 0
        self._error_count = 0

        self._last_build_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error: str | None = None

    def build(self) -> dict[str, Any]:
        """Construit un snapshot complet depuis le Controller."""

        built_at = utc_now_iso()

        with self._lock:
            self._build_count += 1
            self._last_build_at = built_at

        try:
            payload = self.controller._build_status_snapshot()

            if not isinstance(payload, dict):
                raise TypeError(
                    "_build_status_snapshot() doit retourner "
                    "un dictionnaire."
                )

            result = copy.deepcopy(payload)

            with self._lock:
                self._success_count += 1
                self._last_success_at = built_at
                self._last_error = None

            return result

        except Exception as exc:
            with self._lock:
                self._error_count += 1
                self._last_error_at = built_at
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )

            raise

    def status(self) -> dict[str, Any]:
        """Expose les métriques du constructeur."""

        with self._lock:
            metrics = {
                "build_count": self._build_count,
                "success_count": self._success_count,
                "error_count": self._error_count,
                "last_build_at": self._last_build_at,
                "last_success_at": self._last_success_at,
                "last_error_at": self._last_error_at,
                "last_error": self._last_error,
            }

        if self._last_error is not None:
            overall = "DEGRADED"
        elif self._success_count > 0:
            overall = "OK"
        else:
            overall = "STARTING"

        return {
            "component": "geocooling",
            "view": "snapshot_builder",
            "read_only": True,
            "generated_at": utc_now_iso(),
            "overall": overall,
            "metrics": metrics,
        }
