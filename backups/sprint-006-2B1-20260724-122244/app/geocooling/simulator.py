import threading
from datetime import datetime, timezone
from typing import Any


def utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class SimulationDriver:
    """
    Simule uniquement les deux actionneurs physiques :
    - électrovanne ;
    - circulateur.

    Aucune publication MQTT réelle n'est effectuée.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._valve_open = False
        self._pump_running = False
        self._last_action_at = utc_iso()

    def open_valve(self) -> None:
        with self._lock:
            self._valve_open = True
            self._last_action_at = utc_iso()

    def close_valve(self) -> None:
        with self._lock:
            self._valve_open = False
            self._last_action_at = utc_iso()

    def start_pump(self) -> None:
        with self._lock:
            if not self._valve_open:
                raise RuntimeError(
                    "Le circulateur ne peut pas démarrer "
                    "tant que l'électrovanne est fermée."
                )

            self._pump_running = True
            self._last_action_at = utc_iso()

    def stop_pump(self) -> None:
        with self._lock:
            self._pump_running = False
            self._last_action_at = utc_iso()

    def force_safe_state(self) -> None:
        with self._lock:
            self._pump_running = False
            self._valve_open = False
            self._last_action_at = utc_iso()

    def status(self) -> dict[str, Any]:
        with self._lock:
            return {
                "driver": "simulation",
                "simulation": True,
                "valve_open": self._valve_open,
                "pump_running": self._pump_running,
                "last_action_at": self._last_action_at,
            }
