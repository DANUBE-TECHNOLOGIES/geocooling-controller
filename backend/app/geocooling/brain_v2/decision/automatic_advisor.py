from __future__ import annotations

import json
import logging
import os
import threading
import time

from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from app.geocooling.brain_v2.decision.advisory_decision_engine import (
    AdvisoryDecisionEngine,
)


LOGGER = logging.getLogger(
    "sbc.geocooling.brain_v2.automatic_advisor"
)


class AutomaticAdvisoryOrchestrator:
    VERSION = "C022.6-AUTO-ADVISOR-1.0"

    def __init__(
        self,
        data_directory: str | Path | None = None,
        evaluation_interval_seconds: int | None = None,
        initial_delay_seconds: int | None = None,
    ) -> None:
        configured_directory = (
            data_directory
            or os.getenv(
                "GEOCOOLING_BRAIN_V2_DATA_DIR",
                "/app/data/geocooling/brain_v2",
            )
        )

        self.data_directory = Path(
            configured_directory
        )

        self.data_directory.mkdir(
            parents=True,
            exist_ok=True,
        )

        self.state_path = (
            self.data_directory
            / "automatic-advisor.json"
        )

        self.snapshot_path = (
            self.data_directory
            / "home-assistant-advisory.json"
        )

        self.evaluation_interval_seconds = max(
            int(
                evaluation_interval_seconds
                or os.getenv(
                    "GEOCOOLING_BRAIN_V2_ADVISORY_INTERVAL",
                    "300",
                )
            ),
            60,
        )

        self.initial_delay_seconds = max(
            int(
                initial_delay_seconds
                if initial_delay_seconds is not None
                else os.getenv(
                    "GEOCOOLING_BRAIN_V2_ADVISORY_INITIAL_DELAY",
                    "45",
                )
            ),
            0,
        )

        self.enabled = (
            os.getenv(
                "GEOCOOLING_BRAIN_V2_AUTO_ADVISOR",
                "true",
            ).strip().lower()
            not in {
                "0",
                "false",
                "no",
                "off",
            }
        )

        self.engine = AdvisoryDecisionEngine(
            data_directory=self.data_directory
        )

        self._lock = threading.RLock()
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

        self._state = self._load_state()

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    def _default_state(
        self,
    ) -> dict[str, Any]:
        return {
            "version": self.VERSION,
            "enabled": self.enabled,
            "running": False,
            "evaluation_interval_seconds": (
                self.evaluation_interval_seconds
            ),
            "evaluation_attempts": 0,
            "successful_evaluations": 0,
            "failed_evaluations": 0,
            "last_evaluation_at": None,
            "last_action": None,
            "last_priority": None,
            "last_confidence_percent": None,
            "last_error": None,
            "advisory_only": True,
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        }

    def _load_state(
        self,
    ) -> dict[str, Any]:
        default = self._default_state()

        if not self.state_path.exists():
            return default

        try:
            payload = json.loads(
                self.state_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return default

        if isinstance(payload, dict):
            default.update(payload)

        default.update(
            {
                "version": self.VERSION,
                "enabled": self.enabled,
                "running": False,
                "evaluation_interval_seconds": (
                    self.evaluation_interval_seconds
                ),
                "advisory_only": True,
                "decision_authority": False,
                "hardware_control": False,
                "mqtt_publish": False,
                "modbus_command": False,
                "relay_command": False,
            }
        )

        return default

    @staticmethod
    def _atomic_write(
        path: Path,
        payload: dict[str, Any],
    ) -> None:
        temporary_path = path.with_suffix(
            path.suffix + ".tmp"
        )

        temporary_path.write_text(
            json.dumps(
                payload,
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            )
            + "\n",
            encoding="utf-8",
        )

        os.replace(
            temporary_path,
            path,
        )

    def _save_state(
        self,
    ) -> None:
        self._atomic_write(
            self.state_path,
            self._state,
        )

    @staticmethod
    def _home_assistant_snapshot(
        decision: dict[str, Any],
    ) -> dict[str, Any]:
        context = decision.get(
            "context",
            {},
        ) or {}

        condensation = decision.get(
            "condensation",
            {},
        ) or {}

        prediction = decision.get(
            "prediction",
            {},
        ) or {}

        safety = decision.get(
            "safety",
            {},
        ) or {}

        reasons = decision.get(
            "reasons",
            [],
        ) or []

        return {
            "version": (
                "C022.6-HOME-ASSISTANT-ADVISORY-1.0"
            ),
            "generated_at": decision.get(
                "generated_at"
            ),
            "status": decision.get(
                "status"
            ),
            "action": decision.get(
                "advisory_action"
            ),
            "priority": decision.get(
                "advisory_priority"
            ),
            "summary": decision.get(
                "summary"
            ),
            "confidence_percent": decision.get(
                "confidence_percent"
            ),
            "indoor_temperature_c": context.get(
                "indoor_temperature_c"
            ),
            "outdoor_temperature_c": context.get(
                "outdoor_temperature_c"
            ),
            "floor_surface_temperature_c": context.get(
                "floor_surface_temperature_c"
            ),
            "floor_supply_temperature_c": context.get(
                "floor_supply_temperature_c"
            ),
            "floor_return_temperature_c": context.get(
                "floor_return_temperature_c"
            ),
            "indoor_humidity_percent": context.get(
                "indoor_humidity_percent"
            ),
            "target_temperature_c": decision.get(
                "target_temperature_c"
            ),
            "start_threshold_c": decision.get(
                "start_threshold_c"
            ),
            "stop_threshold_c": decision.get(
                "stop_threshold_c"
            ),
            "active_cooling": context.get(
                "active_cooling"
            ),
            "pump_running": context.get(
                "pump_running"
            ),
            "valve_open": context.get(
                "valve_open"
            ),
            "cooling_benefit_c": decision.get(
                "cooling_benefit_at_horizon_c"
            ),
            "minutes_to_target": decision.get(
                "minutes_to_target"
            ),
            "predicted_cooling_temperature_c": (
                decision.get(
                    "predicted_cooling_temperature_c"
                )
            ),
            "predicted_passive_temperature_c": (
                decision.get(
                    "predicted_passive_temperature_c"
                )
            ),
            "cooling_rate_c_per_hour": prediction.get(
                "cooling_rate_c_per_hour"
            ),
            "passive_rate_c_per_hour": prediction.get(
                "passive_rate_c_per_hour"
            ),
            "observations_used": prediction.get(
                "observations_used"
            ),
            "condensation_status": condensation.get(
                "status"
            ),
            "dew_point_c": condensation.get(
                "dew_point_c"
            ),
            "condensation_margin_c": condensation.get(
                "margin_c"
            ),
            "condensation_safe": condensation.get(
                "safe"
            ),
            "reason_codes": [
                item.get("code")
                for item in reasons
                if isinstance(item, dict)
                and item.get("code")
            ],
            "advisory_only": safety.get(
                "advisory_only",
                True,
            ),
            "decision_authority": False,
            "hardware_control": False,
            "mqtt_publish": False,
            "modbus_command": False,
            "relay_command": False,
        }

    def evaluate_once(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            self._state["evaluation_attempts"] = (
                int(
                    self._state.get(
                        "evaluation_attempts",
                        0,
                    )
                )
                + 1
            )

            try:
                decision = self.engine.evaluate(
                    persist=True
                )

                snapshot = (
                    self._home_assistant_snapshot(
                        decision
                    )
                )

                self._atomic_write(
                    self.snapshot_path,
                    snapshot,
                )

                self._state[
                    "successful_evaluations"
                ] = (
                    int(
                        self._state.get(
                            "successful_evaluations",
                            0,
                        )
                    )
                    + 1
                )

                self._state[
                    "last_evaluation_at"
                ] = decision.get(
                    "generated_at"
                ) or self._utc_now()

                self._state[
                    "last_action"
                ] = decision.get(
                    "advisory_action"
                )

                self._state[
                    "last_priority"
                ] = decision.get(
                    "advisory_priority"
                )

                self._state[
                    "last_confidence_percent"
                ] = decision.get(
                    "confidence_percent"
                )

                self._state["last_error"] = None

                self._save_state()

                return {
                    "result": "ADVISORY_EVALUATED",
                    "decision": decision,
                    "home_assistant": snapshot,
                    "safety": {
                        "advisory_only": True,
                        "decision_authority": False,
                        "hardware_control": False,
                        "mqtt_publish": False,
                        "modbus_command": False,
                        "relay_command": False,
                    },
                }

            except Exception as exc:
                self._state[
                    "failed_evaluations"
                ] = (
                    int(
                        self._state.get(
                            "failed_evaluations",
                            0,
                        )
                    )
                    + 1
                )

                self._state["last_error"] = str(
                    exc
                )

                self._save_state()

                raise

    def latest_snapshot(
        self,
    ) -> dict[str, Any]:
        if not self.snapshot_path.exists():
            return self.evaluate_once()[
                "home_assistant"
            ]

        try:
            payload = json.loads(
                self.snapshot_path.read_text(
                    encoding="utf-8"
                )
            )
        except (
            OSError,
            json.JSONDecodeError,
        ):
            return self.evaluate_once()[
                "home_assistant"
            ]

        if not isinstance(payload, dict):
            return self.evaluate_once()[
                "home_assistant"
            ]

        return payload

    def _background_loop(
        self,
    ) -> None:
        if self.initial_delay_seconds > 0:
            if self._stop_event.wait(
                self.initial_delay_seconds
            ):
                return

        while not self._stop_event.is_set():
            try:
                self.evaluate_once()

            except Exception:
                LOGGER.exception(
                    "Échec évaluation automatique Brain V2"
                )

            self._stop_event.wait(
                self.evaluation_interval_seconds
            )

    def start(
        self,
    ) -> bool:
        with self._lock:
            if not self.enabled:
                self._state["running"] = False
                self._save_state()

                return False

            if (
                self._thread is not None
                and self._thread.is_alive()
            ):
                return True

            self._stop_event.clear()

            self._thread = threading.Thread(
                target=self._background_loop,
                name="brain-v2-auto-advisor",
                daemon=True,
            )

            self._thread.start()

            self._state["running"] = True
            self._state["started_at"] = (
                self._utc_now()
            )
            self._state["last_error"] = None

            self._save_state()

            LOGGER.info(
                "Auto-advisor Brain V2 démarré : intervalle=%ss",
                self.evaluation_interval_seconds,
            )

            return True

    def stop(
        self,
    ) -> None:
        with self._lock:
            self._stop_event.set()
            thread = self._thread

        if (
            thread is not None
            and thread.is_alive()
        ):
            thread.join(
                timeout=5
            )

        with self._lock:
            self._state["running"] = False
            self._state["stopped_at"] = (
                self._utc_now()
            )
            self._save_state()

    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            running = bool(
                self._thread is not None
                and self._thread.is_alive()
            )

            result = dict(
                self._state
            )

            result.update(
                {
                    "version": self.VERSION,
                    "enabled": self.enabled,
                    "running": running,
                    "evaluation_interval_seconds": (
                        self.evaluation_interval_seconds
                    ),
                    "state_path": str(
                        self.state_path
                    ),
                    "snapshot_path": str(
                        self.snapshot_path
                    ),
                    "state_exists": (
                        self.state_path.exists()
                    ),
                    "snapshot_exists": (
                        self.snapshot_path.exists()
                    ),
                    "data_directory_writable": (
                        os.access(
                            self.data_directory,
                            os.W_OK,
                        )
                    ),
                    "advisory_only": True,
                    "decision_authority": False,
                    "hardware_control": False,
                    "mqtt_publish": False,
                    "modbus_command": False,
                    "relay_command": False,
                }
            )

            return result
