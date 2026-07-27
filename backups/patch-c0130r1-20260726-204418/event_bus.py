"""Bus d'événements interne du contrôleur GeoCooling.

PATCH C012.0 — GeoCooling Event Bus

Fondation d'observabilité destinée à découpler progressivement les
composants GeoCooling.

Ce composant :

- conserve un historique mémoire borné ;
- attribue une séquence monotone à chaque événement ;
- horodate les événements en UTC ;
- accepte des niveaux INFO, WARN et ERROR ;
- permet un filtrage en lecture ;
- n'exécute aucune action métier ;
- ne commande aucun relais ;
- ne publie rien vers MQTT à ce stade.

Les publications provenant des composants GeoCooling seront ajoutées
progressivement dans les patchs C012.x suivants.
"""

from __future__ import annotations

import copy
import os
import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Retourne l'heure UTC au format ISO 8601."""

    return datetime.now(timezone.utc).isoformat()


def env_int(
    name: str,
    default: int,
    minimum: int,
    maximum: int,
) -> int:
    """Lit un entier d'environnement avec bornes de sécurité."""

    try:
        value = int(os.getenv(name, str(default)))
    except (TypeError, ValueError):
        value = default

    return max(
        minimum,
        min(maximum, value),
    )


class GeoCoolingEventBus:
    """Bus d'événements mémoire, thread-safe et en lecture seule côté API."""

    VALID_LEVELS = {
        "INFO",
        "WARN",
        "ERROR",
    }

    def __init__(
        self,
        capacity: int | None = None,
    ) -> None:
        configured_capacity = (
            capacity
            if capacity is not None
            else env_int(
                "GEOCOOLING_EVENT_BUS_CAPACITY",
                default=1000,
                minimum=100,
                maximum=50000,
            )
        )

        try:
            normalized_capacity = int(
                configured_capacity
            )
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "La capacité du bus doit être un entier."
            ) from exc

        self.capacity = max(
            1,
            min(50000, normalized_capacity),
        )

        self._lock = threading.RLock()

        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.capacity
        )

        self._created_at = utc_now_iso()
        self._sequence = 0
        self._published_count = 0
        self._dropped_count = 0

        self._info_count = 0
        self._warn_count = 0
        self._error_count = 0

        self._last_event_at: str | None = None
        self._last_source: str | None = None
        self._last_type: str | None = None
        self._last_level: str | None = None

    @staticmethod
    def _normalize_text(
        value: Any,
        field_name: str,
    ) -> str:
        if value is None:
            raise ValueError(
                f"{field_name} est obligatoire."
            )

        text = str(value).strip()

        if not text:
            raise ValueError(
                f"{field_name} ne peut pas être vide."
            )

        if len(text) > 200:
            raise ValueError(
                f"{field_name} dépasse 200 caractères."
            )

        return text

    @classmethod
    def _normalize_level(
        cls,
        level: Any,
    ) -> str:
        normalized = str(level or "INFO").strip().upper()

        if normalized not in cls.VALID_LEVELS:
            raise ValueError(
                "Niveau invalide. Valeurs autorisées : "
                + ", ".join(sorted(cls.VALID_LEVELS))
            )

        return normalized

    @staticmethod
    def _normalize_payload(
        payload: Any,
    ) -> dict[str, Any]:
        if payload is None:
            return {}

        if not isinstance(payload, dict):
            raise TypeError(
                "Le payload d'un événement doit être "
                "un dictionnaire."
            )

        return copy.deepcopy(payload)

    def publish(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        level: str = "INFO",
    ) -> dict[str, Any]:
        """Publie un événement et retourne une copie de celui-ci."""

        normalized_type = self._normalize_text(
            event_type,
            "event_type",
        )

        normalized_source = self._normalize_text(
            source,
            "source",
        )

        normalized_level = self._normalize_level(
            level
        )

        normalized_payload = self._normalize_payload(
            payload
        )

        published_at = utc_now_iso()

        with self._lock:
            was_full = len(self._events) >= self.capacity

            self._sequence += 1

            event = {
                "sequence": self._sequence,
                "published_at": published_at,
                "type": normalized_type,
                "source": normalized_source,
                "level": normalized_level,
                "payload": normalized_payload,
            }

            self._events.append(event)

            self._published_count += 1

            if was_full:
                self._dropped_count += 1

            if normalized_level == "INFO":
                self._info_count += 1
            elif normalized_level == "WARN":
                self._warn_count += 1
            elif normalized_level == "ERROR":
                self._error_count += 1

            self._last_event_at = published_at
            self._last_source = normalized_source
            self._last_type = normalized_type
            self._last_level = normalized_level

            return copy.deepcopy(event)

    def events(
        self,
        limit: int = 100,
        source: str | None = None,
        event_type: str | None = None,
        level: str | None = None,
        after_sequence: int | None = None,
    ) -> dict[str, Any]:
        """Retourne les événements récents avec filtres facultatifs."""

        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError):
            normalized_limit = 100

        normalized_limit = max(
            1,
            min(
                normalized_limit,
                self.capacity,
            ),
        )

        normalized_source = (
            str(source).strip()
            if source is not None
            else None
        )

        normalized_type = (
            str(event_type).strip()
            if event_type is not None
            else None
        )

        normalized_level = (
            self._normalize_level(level)
            if level is not None
            else None
        )

        if after_sequence is None:
            normalized_after_sequence = None
        else:
            try:
                normalized_after_sequence = int(
                    after_sequence
                )
            except (TypeError, ValueError):
                normalized_after_sequence = 0

            normalized_after_sequence = max(
                0,
                normalized_after_sequence,
            )

        with self._lock:
            selected: list[dict[str, Any]] = []

            for event in reversed(self._events):
                if (
                    normalized_source is not None
                    and event["source"]
                    != normalized_source
                ):
                    continue

                if (
                    normalized_type is not None
                    and event["type"]
                    != normalized_type
                ):
                    continue

                if (
                    normalized_level is not None
                    and event["level"]
                    != normalized_level
                ):
                    continue

                if (
                    normalized_after_sequence is not None
                    and event["sequence"]
                    <= normalized_after_sequence
                ):
                    continue

                selected.append(
                    copy.deepcopy(event)
                )

                if len(selected) >= normalized_limit:
                    break

            return {
                "component": "geocooling",
                "view": "event_bus_events",
                "read_only": True,
                "generated_at": utc_now_iso(),
                "capacity": self.capacity,
                "stored_count": len(self._events),
                "returned_count": len(selected),
                "latest_sequence": self._sequence,
                "filters": {
                    "source": normalized_source,
                    "type": normalized_type,
                    "level": normalized_level,
                    "after_sequence":
                        normalized_after_sequence,
                },
                "items": selected,
            }

    def status(self) -> dict[str, Any]:
        """Expose l'état opérationnel et les métriques du bus."""

        with self._lock:
            stored_count = len(self._events)

            metrics = {
                "sequence": self._sequence,
                "stored_count": stored_count,
                "published_count":
                    self._published_count,
                "dropped_count":
                    self._dropped_count,
                "info_count": self._info_count,
                "warn_count": self._warn_count,
                "error_count": self._error_count,
                "last_event_at":
                    self._last_event_at,
                "last_source": self._last_source,
                "last_type": self._last_type,
                "last_level": self._last_level,
            }

        return {
            "component": "geocooling",
            "view": "event_bus",
            "read_only": True,
            "generated_at": utc_now_iso(),
            "overall": "OK",
            "running": True,
            "ready": True,
            "lifecycle": {
                "created_at": self._created_at,
            },
            "configuration": {
                "capacity": self.capacity,
                "valid_levels": sorted(
                    self.VALID_LEVELS
                ),
                "persistence": False,
                "mqtt_export": False,
                # PATCH C012.1 — Automatic Publishers Metadata
                "automatic_publishers": True,
                "publishers": [
                    "snapshot_builder",
                    "state_cache",  # PATCH C012.2 — State Cache Publisher Metadata
                    "brain",  # PATCH C012.3R4 — Brain Publisher Metadata
                    "predictor",  # PATCH C012.4R1 — Predictor Publisher Metadata
                ],
                "event_types": [
                    "snapshot.created",
                    "state.updated",
                    "brain.decision",
                    "prediction.updated",
                ],
            },
            "metrics": metrics,
        }
