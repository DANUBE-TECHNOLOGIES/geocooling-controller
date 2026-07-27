"""Cache mémoire partagé de l'état GeoCooling.

PATCH C008A v2

Ce composant appelle périodiquement controller.status() et conserve le dernier
résultat valide en mémoire.

Il n'envoie aucune commande au Controller et ne réalise aucune écriture en
base de données.
"""

from __future__ import annotations

import copy
import os
import threading
import time
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def env_float(
    name: str,
    default: float,
    minimum: float,
    maximum: float,
) -> float:
    try:
        value = float(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default

    return max(minimum, min(maximum, value))


class GeoCoolingStateCache:
    """Cache thread-safe du dernier controller.status()."""

    def __init__(
        self,
        controller: Any,
        *,
        interval_seconds: float | None = None,
        autostart: bool = True,
    ) -> None:
        if controller is None:
            raise ValueError("Un Controller est requis.")

        self.controller = controller

        self.interval_seconds = (
            float(interval_seconds)
            if interval_seconds is not None
            else env_float(
                "GEOCOOLING_STATE_CACHE_INTERVAL_SECONDS",
                default=1.0,
                minimum=0.2,
                maximum=60.0,
            )
        )

        self.stale_after_seconds = env_float(
            "GEOCOOLING_STATE_CACHE_STALE_SECONDS",
            default=max(5.0, self.interval_seconds * 3.0),
            minimum=1.0,
            maximum=600.0,
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._worker: threading.Thread | None = None

        self._snapshot: dict[str, Any] | None = None

        self._created_at = utc_now_iso()
        self._started_at: str | None = None
        self._last_capture_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error: str | None = None

        self._sequence = 0
        self._capture_count = 0
        self._success_count = 0
        self._error_count = 0

        if autostart:
            self.start()

    @property
    def running(self) -> bool:
        worker = self._worker

        return bool(
            worker is not None
            and worker.is_alive()
            and not self._stop_event.is_set()
        )

    def start(self) -> None:
        with self._lock:
            if self._worker is not None and self._worker.is_alive():
                return

            self._stop_event.clear()
            self._started_at = utc_now_iso()

            self._worker = threading.Thread(
                target=self._run,
                name="GeoCoolingStateCache",
                daemon=True,
            )

            self._worker.start()

    def stop(self, timeout: float = 5.0) -> None:
        self._stop_event.set()

        worker = self._worker

        if (
            worker is not None
            and worker.is_alive()
            and worker is not threading.current_thread()
        ):
            worker.join(timeout=max(0.0, float(timeout)))

    def _run(self) -> None:
        while not self._stop_event.is_set():
            self.capture()

            self._stop_event.wait(
                timeout=self.interval_seconds
            )

    def _c0122_original_capture(self) -> dict[str, Any]:
        """Appelle une seule fois controller.status()."""

        captured_at = utc_now_iso()

        with self._lock:
            self._capture_count += 1

        try:
            controller_state = self.controller.status()

            if not isinstance(controller_state, dict):
                raise TypeError(
                    "controller.status() n'a pas retourné un dictionnaire."
                )

            with self._lock:
                self._sequence += 1
                self._success_count += 1
                self._last_capture_at = captured_at
                self._last_success_at = captured_at
                self._last_error = None

                self._snapshot = {
                    "sequence": self._sequence,
                    "captured_at": captured_at,
                    "controller": copy.deepcopy(controller_state),
                }

                return copy.deepcopy(self._snapshot)

        except Exception as exc:
            error = f"{type(exc).__name__}: {exc}"

            with self._lock:
                self._error_count += 1
                self._last_capture_at = captured_at
                self._last_error_at = captured_at
                self._last_error = error

            return {
                "captured_at": captured_at,
                "success": False,
                "error": error,
            }

    def latest(self) -> dict[str, Any] | None:
        with self._lock:
            if self._snapshot is None:
                return None

            snapshot = copy.deepcopy(self._snapshot)

        captured_at = snapshot.get("captured_at")
        age_seconds: float | None = None

        if isinstance(captured_at, str):
            try:
                parsed = datetime.fromisoformat(
                    captured_at.replace("Z", "+00:00")
                )

                if parsed.tzinfo is None:
                    parsed = parsed.replace(tzinfo=timezone.utc)

                age_seconds = max(
                    0.0,
                    (
                        datetime.now(timezone.utc)
                        - parsed.astimezone(timezone.utc)
                    ).total_seconds(),
                )
            except ValueError:
                age_seconds = None

        snapshot["age_seconds"] = age_seconds
        snapshot["stale"] = bool(
            age_seconds is None
            or age_seconds > self.stale_after_seconds
        )

        return snapshot

    def wait_until_ready(self, timeout: float = 10.0) -> bool:
        deadline = time.monotonic() + max(0.0, float(timeout))

        while time.monotonic() < deadline:
            with self._lock:
                if self._snapshot is not None:
                    return True

            if not self.running:
                return False

            time.sleep(0.05)

        with self._lock:
            return self._snapshot is not None

    def status(
        self,
        *,
        include_controller: bool = True,
    ) -> dict[str, Any]:
        snapshot = self.latest()

        with self._lock:
            metrics = {
                "capture_count": self._capture_count,
                "success_count": self._success_count,
                "error_count": self._error_count,
                "sequence": self._sequence,
                "last_capture_at": self._last_capture_at,
                "last_success_at": self._last_success_at,
                "last_error_at": self._last_error_at,
                "last_error": self._last_error,
            }

        if snapshot is None:
            overall = "STARTING" if self.running else "CRITICAL"

        elif snapshot.get("stale"):
            overall = "DEGRADED"

        elif self._last_error is not None:
            overall = "DEGRADED"

        else:
            overall = "OK"

        if snapshot is not None and not include_controller:
            snapshot.pop("controller", None)

        return {
            "component": "geocooling",
            "view": "state_cache",
            "read_only": True,
            "generated_at": utc_now_iso(),
            "overall": overall,
            "running": self.running,
            "ready": snapshot is not None,
            "configuration": {
                "interval_seconds": self.interval_seconds,
                "stale_after_seconds": self.stale_after_seconds,
            },
            "lifecycle": {
                "created_at": self._created_at,
                "started_at": self._started_at,
            },
            "metrics": metrics,
            "snapshot": snapshot,
        }


    # PATCH C012.2 — State Updated Publisher
    def _c0122_sequence_value(self) -> int:
        """Retourne la séquence actuelle du cache."""

        for attribute_name in (
            "_sequence",
            "sequence",
            "_snapshot_sequence",
            "snapshot_sequence",
        ):
            value = getattr(
                self,
                attribute_name,
                None,
            )

            try:
                return int(value)
            except (TypeError, ValueError):
                continue

        try:
            status = self.status(
                include_controller=False
            )
        except TypeError:
            try:
                status = self.status()
            except Exception:
                return 0
        except Exception:
            return 0

        if not isinstance(status, dict):
            return 0

        metrics = status.get(
            "metrics",
            {},
        )

        if not isinstance(metrics, dict):
            return 0

        try:
            return int(
                metrics.get("sequence", 0)
            )
        except (TypeError, ValueError):
            return 0

    def _c0122_publish_state_updated(
        self,
        previous_sequence: int,
    ) -> dict[str, Any] | None:
        """Publie state.updated après un vrai rafraîchissement."""

        try:
            current_sequence = (
                self._c0122_sequence_value()
            )

            if current_sequence <= previous_sequence:
                return None

            event_bus = getattr(
                self,
                "_event_bus",
                None,
            )

            if event_bus is None:
                controller = getattr(
                    self,
                    "controller",
                    None,
                )

                if controller is None:
                    controller = getattr(
                        self,
                        "_controller",
                        None,
                    )

                event_bus = getattr(
                    controller,
                    "event_bus",
                    None,
                )

            if event_bus is None:
                return None

            try:
                cache_status = self.status(
                    include_controller=False
                )
            except TypeError:
                cache_status = self.status()

            if not isinstance(cache_status, dict):
                cache_status = {}

            metrics = cache_status.get(
                "metrics",
                {},
            )

            snapshot = cache_status.get(
                "snapshot",
                {},
            )

            if not isinstance(metrics, dict):
                metrics = {}

            if not isinstance(snapshot, dict):
                snapshot = {}

            payload = {
                "sequence": current_sequence,
                "previous_sequence": previous_sequence,
                "captured_at": snapshot.get(
                    "captured_at"
                ),
                "age_seconds": snapshot.get(
                    "age_seconds"
                ),
                "stale": snapshot.get("stale"),
                "ready": cache_status.get("ready"),
                "running": cache_status.get("running"),
                "error_count": metrics.get(
                    "error_count"
                ),
                "refresh_count": metrics.get(
                    "refresh_count",
                    metrics.get("capture_count"),
                ),
            }

            controller_snapshot = snapshot.get(
                "controller"
            )

            if isinstance(controller_snapshot, dict):
                payload["state"] = (
                    controller_snapshot.get("state")
                )

                payload["mode"] = (
                    controller_snapshot.get("mode")
                )

            payload = {
                key: value
                for key, value in payload.items()
                if value is not None
            }

            return event_bus.publish(
                event_type="state.updated",
                source="state_cache",
                payload=payload,
                level="INFO",
            )

        except Exception:
            return None

    def capture(self, *args: Any, **kwargs: Any) -> Any:
        """Exécute le rafraîchissement puis publie state.updated."""

        previous_sequence = (
            self._c0122_sequence_value()
        )

        result = self._c0122_original_capture(
            *args,
            **kwargs,
        )

        self._c0122_publish_state_updated(
            previous_sequence
        )

        return result
