"""Construction centralisée et contrôlée du snapshot GeoCooling.

PATCH C011A — Snapshot Builder
PATCH C011C — Snapshot Integrity
PATCH C011D.1 — Snapshot Memory History

Le composant construit une représentation cohérente de l'état courant
du Controller.

Il ne pilote aucun relais et ne modifie aucun état opérationnel.

C011C ajoute :

- une empreinte SHA-256 du contenu ;
- une empreinte SHA-256 de la structure ;
- un contrôle non bloquant de cohérence ;
- la durée et la taille de chaque construction ;
- la détection des changements de structure.
"""

from __future__ import annotations

import copy
import hashlib
import json
import threading
import time
from collections import deque
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingSnapshotBuilder:
    """Façade thread-safe de construction du snapshot Controller."""

    REQUIRED_TOP_LEVEL_FIELDS = (
        "component",
        "state",
        "mode",
        "device",
        "safety",
        "thermal",
        "brain",
        "prediction",
    )

    REQUIRED_MAPPING_FIELDS = (
        "device",
        "safety",
        "thermal",
        "brain",
        "prediction",
    )

    def __init__(self, controller: Any) -> None:
        if controller is None:
            raise ValueError("Un Controller est requis.")

        self.controller = controller
        self._lock = threading.RLock()

        self._created_at = utc_now_iso()

        self.history_capacity = 500
        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )
        self._history_sequence = 0

        self._build_count = 0
        self._success_count = 0
        self._error_count = 0
        self._coherent_count = 0
        self._incoherent_count = 0

        self._payload_change_count = 0
        self._structure_change_count = 0

        self._last_build_at: str | None = None
        self._last_success_at: str | None = None
        self._last_error_at: str | None = None
        self._last_error: str | None = None

        self._last_coherent: bool | None = None
        self._last_coherence_issues: list[str] = []

        self._last_payload_fingerprint: str | None = None
        self._previous_payload_fingerprint: str | None = None

        self._last_structure_fingerprint: str | None = None
        self._previous_structure_fingerprint: str | None = None

        self._last_size_bytes: int | None = None
        self._last_duration_ms: float | None = None
        self._maximum_duration_ms: float = 0.0

    @staticmethod
    def _canonical_json(value: Any) -> bytes:
        """Retourne une représentation JSON déterministe."""

        payload = json.dumps(
            value,
            ensure_ascii=False,
            sort_keys=True,
            separators=(",", ":"),
            default=str,
        )

        return payload.encode("utf-8")

    @classmethod
    def _fingerprint(cls, value: Any) -> str:
        return hashlib.sha256(
            cls._canonical_json(value)
        ).hexdigest()

    @classmethod
    def _structure_descriptor(
        cls,
        value: Any,
    ) -> Any:
        """Décrit uniquement la structure et les types du snapshot."""

        if isinstance(value, dict):
            return {
                str(key): cls._structure_descriptor(
                    child
                )
                for key, child in sorted(
                    value.items(),
                    key=lambda item: str(item[0]),
                )
            }

        if isinstance(value, list):
            descriptors = [
                cls._structure_descriptor(item)
                for item in value
            ]

            unique: dict[str, Any] = {}

            for descriptor in descriptors:
                encoded = json.dumps(
                    descriptor,
                    ensure_ascii=False,
                    sort_keys=True,
                    separators=(",", ":"),
                    default=str,
                )

                unique[encoded] = descriptor

            return {
                "type": "list",
                "item_types": [
                    unique[key]
                    for key in sorted(unique)
                ],
            }

        if value is None:
            return "null"

        if isinstance(value, bool):
            return "boolean"

        if isinstance(value, int):
            return "integer"

        if isinstance(value, float):
            return "number"

        if isinstance(value, str):
            return "string"

        return type(value).__name__

    @classmethod
    def _validate_coherence(
        cls,
        snapshot: dict[str, Any],
    ) -> list[str]:
        """Retourne les incohérences détectées sans bloquer le snapshot."""

        issues: list[str] = []

        for field in cls.REQUIRED_TOP_LEVEL_FIELDS:
            if field not in snapshot:
                issues.append(
                    f"missing_top_level_field:{field}"
                )

        component = snapshot.get("component")

        if component != "geocooling":
            issues.append(
                "invalid_component:"
                + repr(component)
            )

        state = snapshot.get("state")

        if not isinstance(state, str) or not state:
            issues.append("invalid_state")

        mode = snapshot.get("mode")

        if not isinstance(mode, str) or not mode:
            issues.append("invalid_mode")

        for field in cls.REQUIRED_MAPPING_FIELDS:
            value = snapshot.get(field)

            if not isinstance(value, dict):
                issues.append(
                    f"invalid_mapping:{field}"
                )

        for field in (
            "valve_open",
            "pump_running",
        ):
            if (
                field in snapshot
                and not isinstance(
                    snapshot.get(field),
                    bool,
                )
            ):
                issues.append(
                    f"invalid_boolean:{field}"
                )

        device = snapshot.get("device")

        if isinstance(device, dict):
            for field in (
                "ready",
                "simulation",
            ):
                if (
                    field in device
                    and not isinstance(
                        device.get(field),
                        bool,
                    )
                ):
                    issues.append(
                        f"invalid_device_boolean:{field}"
                    )

        safety = snapshot.get("safety")

        if isinstance(safety, dict):
            if (
                "safe" in safety
                and not isinstance(
                    safety.get("safe"),
                    bool,
                )
            ):
                issues.append(
                    "invalid_safety_boolean:safe"
                )

        thermal = snapshot.get("thermal")

        if isinstance(thermal, dict):
            if (
                "available" in thermal
                and not isinstance(
                    thermal.get("available"),
                    bool,
                )
            ):
                issues.append(
                    "invalid_thermal_boolean:available"
                )

        brain = snapshot.get("brain")

        if isinstance(brain, dict):
            decision = brain.get("decision")

            if (
                decision is not None
                and not isinstance(decision, str)
            ):
                issues.append(
                    "invalid_brain_decision"
                )

        prediction = snapshot.get("prediction")

        if isinstance(prediction, dict):
            source = prediction.get("input_source")

            if (
                source is not None
                and source not in {
                    "live",
                    "state_cache",
                }
            ):
                issues.append(
                    "invalid_prediction_input_source:"
                    + repr(source)
                )

        return issues

    def _record_history(
        self,
        *,
        built_at: str,
        coherent: bool,
        issues: list[str],
        payload_fingerprint: str,
        structure_fingerprint: str,
        payload_changed: bool,
        structure_changed: bool,
        size_bytes: int,
        duration_ms: float,
        snapshot: dict[str, Any],
    ) -> None:
        """Enregistre un résumé borné de la construction."""

        device = snapshot.get("device")
        safety = snapshot.get("safety")
        brain = snapshot.get("brain")
        prediction = snapshot.get("prediction")

        if not isinstance(device, dict):
            device = {}

        if not isinstance(safety, dict):
            safety = {}

        if not isinstance(brain, dict):
            brain = {}

        if not isinstance(prediction, dict):
            prediction = {}

        self._history_sequence += 1

        self._history.append(
            {
                "sequence": self._history_sequence,
                "built_at": built_at,
                "coherent": coherent,
                "issues": list(issues),
                "payload_fingerprint":
                    payload_fingerprint,
                "structure_fingerprint":
                    structure_fingerprint,
                "payload_changed": payload_changed,
                "structure_changed":
                    structure_changed,
                "size_bytes": size_bytes,
                "duration_ms": duration_ms,
                "summary": {
                    "state": snapshot.get("state"),
                    "mode": snapshot.get("mode"),
                    "valve_open":
                        snapshot.get("valve_open"),
                    "pump_running":
                        snapshot.get("pump_running"),
                    "device_ready":
                        device.get("ready"),
                    "device_online":
                        device.get("online"),
                    "safety_safe":
                        safety.get("safe"),
                    "safety_level":
                        safety.get("level"),
                    "brain_decision":
                        brain.get("decision"),
                    "prediction_input_source":
                        prediction.get(
                            "input_source"
                        ),
                },
            }
        )

    def _build_snapshot_core(self) -> dict[str, Any]:
        """Construit un snapshot complet depuis le Controller."""

        started_monotonic = time.perf_counter()
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

            canonical = self._canonical_json(result)
            size_bytes = len(canonical)

            payload_fingerprint = hashlib.sha256(
                canonical
            ).hexdigest()

            structure = self._structure_descriptor(result)
            structure_fingerprint = self._fingerprint(
                structure
            )

            coherence_issues = self._validate_coherence(
                result
            )

            coherent = not coherence_issues

            duration_ms = round(
                (
                    time.perf_counter()
                    - started_monotonic
                )
                * 1000.0,
                3,
            )

            with self._lock:
                previous_payload = (
                    self._last_payload_fingerprint
                )
                previous_structure = (
                    self._last_structure_fingerprint
                )

                self._previous_payload_fingerprint = (
                    previous_payload
                )
                self._previous_structure_fingerprint = (
                    previous_structure
                )

                if (
                    previous_payload is not None
                    and previous_payload
                    != payload_fingerprint
                ):
                    self._payload_change_count += 1

                if (
                    previous_structure is not None
                    and previous_structure
                    != structure_fingerprint
                ):
                    self._structure_change_count += 1

                self._last_payload_fingerprint = (
                    payload_fingerprint
                )
                self._last_structure_fingerprint = (
                    structure_fingerprint
                )

                self._last_size_bytes = size_bytes
                self._last_duration_ms = duration_ms
                self._maximum_duration_ms = max(
                    self._maximum_duration_ms,
                    duration_ms,
                )

                self._last_coherent = coherent
                self._last_coherence_issues = list(
                    coherence_issues
                )

                if coherent:
                    self._coherent_count += 1
                else:
                    self._incoherent_count += 1

                self._success_count += 1
                self._last_success_at = built_at
                self._last_error = None

                self._record_history(
                    built_at=built_at,
                    coherent=coherent,
                    issues=coherence_issues,
                    payload_fingerprint=(
                        payload_fingerprint
                    ),
                    structure_fingerprint=(
                        structure_fingerprint
                    ),
                    payload_changed=bool(
                        previous_payload is not None
                        and previous_payload
                        != payload_fingerprint
                    ),
                    structure_changed=bool(
                        previous_structure is not None
                        and previous_structure
                        != structure_fingerprint
                    ),
                    size_bytes=size_bytes,
                    duration_ms=duration_ms,
                    snapshot=result,
                )

            return result

        except Exception as exc:
            duration_ms = round(
                (
                    time.perf_counter()
                    - started_monotonic
                )
                * 1000.0,
                3,
            )

            with self._lock:
                self._error_count += 1
                self._last_error_at = built_at
                self._last_error = (
                    f"{type(exc).__name__}: {exc}"
                )
                self._last_duration_ms = duration_ms
                self._maximum_duration_ms = max(
                    self._maximum_duration_ms,
                    duration_ms,
                )

            raise

    def history(
        self,
        limit: int = 100,
    ) -> dict[str, Any]:
        """Expose les dernières constructions en mémoire."""

        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            normalized_limit = 100

        normalized_limit = max(
            1,
            min(
                normalized_limit,
                self.history_capacity,
            ),
        )

        with self._lock:
            items = list(self._history)[
                -normalized_limit:
            ]

            items.reverse()

            return {
                "component": "geocooling",
                "view": "snapshot_builder_history",
                "read_only": True,
                "generated_at": utc_now_iso(),
                "capacity": self.history_capacity,
                "stored_count": len(self._history),
                "returned_count": len(items),
                "latest_sequence":
                    self._history_sequence,
                "items": copy.deepcopy(items),
            }

    def status(self) -> dict[str, Any]:
        """Expose les métriques et l'intégrité du constructeur."""

        with self._lock:
            metrics = {
                "build_count": self._build_count,
                "success_count": self._success_count,
                "error_count": self._error_count,
                "coherent_count": self._coherent_count,
                "incoherent_count":
                    self._incoherent_count,
                "payload_change_count":
                    self._payload_change_count,
                "structure_change_count":
                    self._structure_change_count,
                "history_count": len(self._history),
                "history_sequence":
                    self._history_sequence,
                "last_build_at": self._last_build_at,
                "last_success_at":
                    self._last_success_at,
                "last_error_at": self._last_error_at,
                "last_error": self._last_error,
                "last_size_bytes":
                    self._last_size_bytes,
                "last_duration_ms":
                    self._last_duration_ms,
                "maximum_duration_ms":
                    round(
                        self._maximum_duration_ms,
                        3,
                    ),
            }

            integrity = {
                "coherent": self._last_coherent,
                "issues": list(
                    self._last_coherence_issues
                ),
                "payload_fingerprint": (
                    self._last_payload_fingerprint
                ),
                "previous_payload_fingerprint": (
                    self._previous_payload_fingerprint
                ),
                "payload_changed": bool(
                    self._previous_payload_fingerprint
                    is not None
                    and self._last_payload_fingerprint
                    != self._previous_payload_fingerprint
                ),
                "structure_fingerprint": (
                    self._last_structure_fingerprint
                ),
                "previous_structure_fingerprint": (
                    self._previous_structure_fingerprint
                ),
                "structure_changed": bool(
                    self._previous_structure_fingerprint
                    is not None
                    and self._last_structure_fingerprint
                    != self._previous_structure_fingerprint
                ),
                "algorithm": "sha256",
                "canonicalization": (
                    "json-sort-keys-compact"
                ),
            }

        if self._last_error is not None:
            overall = "DEGRADED"
        elif self._last_coherent is False:
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
            "lifecycle": {
                "created_at": self._created_at,
            },
            "configuration": {
                "required_top_level_fields": list(
                    self.REQUIRED_TOP_LEVEL_FIELDS
                ),
                "required_mapping_fields": list(
                    self.REQUIRED_MAPPING_FIELDS
                ),
                "coherence_validation": "non_blocking",
                "history_capacity":
                    self.history_capacity,
            },
            "metrics": metrics,
            "integrity": integrity,
        }

    # PATCH C012.1 — Snapshot Created Publisher
    def _publish_snapshot_created(
        self,
        snapshot: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Publie un événement après une construction réussie.

        Une panne du bus d'événements ne doit jamais interrompre la
        construction du snapshot principal.
        """

        try:
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

            builder_status = self.status()

            metrics = builder_status.get(
                "metrics",
                {},
            )

            payload = {
                "build_count": metrics.get(
                    "build_count"
                ),
                "success_count": metrics.get(
                    "success_count"
                ),
                "history_sequence": metrics.get(
                    "history_sequence"
                ),
                "history_count": metrics.get(
                    "history_count"
                ),
                "payload_fingerprint": metrics.get(
                    "payload_fingerprint"
                ),
                "structure_fingerprint": metrics.get(
                    "structure_fingerprint"
                ),
                "snapshot_size_bytes": metrics.get(
                    "snapshot_size_bytes"
                ),
                "build_duration_ms": metrics.get(
                    "build_duration_ms"
                ),
                "coherent": metrics.get(
                    "coherent",
                    True,
                ),
            }

            if isinstance(snapshot, dict):
                payload["snapshot_component"] = (
                    snapshot.get("component")
                )

                payload["snapshot_view"] = (
                    snapshot.get("view")
                )

                payload["snapshot_state"] = (
                    snapshot.get("state")
                )

                payload["snapshot_mode"] = (
                    snapshot.get("mode")
                )

            payload = {
                key: value
                for key, value in payload.items()
                if value is not None
            }

            return event_bus.publish(
                event_type="snapshot.created",
                source="snapshot_builder",
                payload=payload,
                level="INFO",
            )

        except Exception:
            return None

    def build(self) -> dict[str, Any]:
        """Construit le snapshot et publie snapshot.created."""

        snapshot = self._build_snapshot_core()

        self._publish_snapshot_created(
            snapshot
        )

        return snapshot
