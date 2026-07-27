"""Chronologie unifiée des événements GeoCooling.

Cette vue agrège les données existantes sans modifier le fonctionnement du
Controller, du Brain, du Driver ou des actionneurs.

Sources utilisées :

- BrainMemory / PostgreSQL ;
- décisions du Brain ;
- commandes manuelles ;
- instantanés du Flight Recorder ;
- tests de commissioning.

Le module est strictement en lecture seule.
"""

from __future__ import annotations

import copy
import hashlib
import json
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def utc_now_iso() -> str:
    return utc_now().isoformat()


def json_safe(value: Any) -> Any:
    if value is None:
        return None

    if isinstance(
        value,
        (
            str,
            int,
            float,
            bool,
        ),
    ):
        return value

    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(
                tzinfo=timezone.utc
            )

        return value.astimezone(
            timezone.utc
        ).isoformat()

    if isinstance(value, dict):
        return {
            str(key): json_safe(item)
            for key, item in value.items()
        }

    if isinstance(
        value,
        (
            list,
            tuple,
            set,
        ),
    ):
        return [
            json_safe(item)
            for item in value
        ]

    enum_value = getattr(
        value,
        "value",
        None,
    )

    if enum_value is not None and not callable(
        enum_value
    ):
        return json_safe(enum_value)

    isoformat_method = getattr(
        value,
        "isoformat",
        None,
    )

    if callable(isoformat_method):
        try:
            return isoformat_method()
        except Exception:
            pass

    return str(value)


def parse_datetime(value: Any) -> datetime | None:
    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, str):
        normalized = value.strip()

        if not normalized:
            return None

        if normalized.endswith("Z"):
            normalized = (
                normalized[:-1]
                + "+00:00"
            )

        try:
            parsed = datetime.fromisoformat(
                normalized
            )
        except ValueError:
            return None

    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc
        )

    return parsed.astimezone(
        timezone.utc
    )


class GeoCoolingEventTimeline:
    """Construit une chronologie unifiée et ordonnée."""

    def __init__(
        self,
        controller: Any,
        flight_recorder: Any,
        commissioning_test_manager: Any,
    ) -> None:
        self.controller = controller
        self.flight_recorder = flight_recorder
        self.commissioning_test_manager = (
            commissioning_test_manager
        )

    @staticmethod
    def _mapping(
        value: Any,
    ) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    @staticmethod
    def _list(
        value: Any,
    ) -> list[Any]:
        if isinstance(value, list):
            return value

        if isinstance(value, tuple):
            return list(value)

        return []

    @staticmethod
    def _event_id(
        source: str,
        event_type: str,
        occurred_at: str,
        payload: dict[str, Any],
    ) -> str:
        raw = json.dumps(
            {
                "source": source,
                "event_type": event_type,
                "occurred_at": occurred_at,
                "payload": json_safe(payload),
            },
            sort_keys=True,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")

        digest = hashlib.sha256(
            raw
        ).hexdigest()[:20]

        return f"{source}-{digest}"

    def _event(
        self,
        *,
        source: str,
        event_type: str,
        occurred_at: Any,
        severity: str = "INFO",
        title: str,
        message: str,
        payload: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        parsed = parse_datetime(
            occurred_at
        )

        if parsed is None:
            parsed = utc_now()

        occurred_at_iso = (
            parsed.isoformat()
        )

        safe_payload = json_safe(
            payload or {}
        )

        normalized_severity = str(
            severity
        ).upper()

        if normalized_severity not in {
            "DEBUG",
            "INFO",
            "WARNING",
            "ERROR",
            "CRITICAL",
        }:
            normalized_severity = "INFO"

        return {
            "id": self._event_id(
                source,
                event_type,
                occurred_at_iso,
                safe_payload,
            ),
            "source": source,
            "type": event_type,
            "occurred_at": occurred_at_iso,
            "severity": normalized_severity,
            "title": title,
            "message": message,
            "payload": safe_payload,
        }

    def _memory(self) -> Any | None:
        for attribute in (
            "brain_memory",
            "memory",
            "_brain_memory",
            "_memory",
        ):
            candidate = getattr(
                self.controller,
                attribute,
                None,
            )

            if candidate is not None:
                return candidate

        brain = getattr(
            self.controller,
            "brain",
            None,
        )

        if brain is not None:
            for attribute in (
                "memory",
                "brain_memory",
                "_memory",
            ):
                candidate = getattr(
                    brain,
                    attribute,
                    None,
                )

                if candidate is not None:
                    return candidate

        return None

    @staticmethod
    def _call_list_method(
        instance: Any,
        method_names: tuple[str, ...],
        limit: int,
    ) -> list[dict[str, Any]]:
        if instance is None:
            return []

        for method_name in method_names:
            method = getattr(
                instance,
                method_name,
                None,
            )

            if not callable(method):
                continue

            try:
                try:
                    result = method(
                        limit=limit
                    )
                except TypeError:
                    result = method(limit)

                if isinstance(result, list):
                    return [
                        json_safe(item)
                        for item in result
                        if isinstance(item, dict)
                    ]

            except Exception:
                continue

        return []

    def _memory_events(
        self,
        limit: int,
    ) -> list[dict[str, Any]]:
        memory = self._memory()

        rows = self._call_list_method(
            memory,
            (
                "recent_events",
                "get_recent_events",
                "list_recent_events",
            ),
            limit,
        )

        events: list[dict[str, Any]] = []

        for row in rows:
            event_type = str(
                row.get(
                    "event_type",
                    row.get(
                        "type",
                        row.get(
                            "name",
                            "geocooling.event",
                        ),
                    ),
                )
            )

            occurred_at = (
                row.get("created_at")
                or row.get("occurred_at")
                or row.get("timestamp")
                or row.get("generated_at")
                or utc_now_iso()
            )

            severity = str(
                row.get(
                    "severity",
                    row.get(
                        "level",
                        "INFO",
                    ),
                )
            ).upper()

            title = str(
                row.get(
                    "title",
                    event_type,
                )
            )

            message = str(
                row.get(
                    "message",
                    row.get(
                        "reason",
                        title,
                    ),
                )
            )

            events.append(
                self._event(
                    source="brain_memory",
                    event_type=event_type,
                    occurred_at=occurred_at,
                    severity=severity,
                    title=title,
                    message=message,
                    payload=row,
                )
            )

        return events

    def _brain_decisions(
        self,
        limit: int,
    ) -> list[dict[str, Any]]:
        memory = self._memory()

        rows = self._call_list_method(
            memory,
            (
                "recent_decisions",
                "get_recent_decisions",
                "list_recent_decisions",
            ),
            limit,
        )

        events: list[dict[str, Any]] = []

        for row in rows:
            decision = str(
                row.get(
                    "decision",
                    row.get(
                        "action",
                        "UNKNOWN",
                    ),
                )
            )

            occurred_at = (
                row.get("created_at")
                or row.get("generated_at")
                or row.get("timestamp")
                or utc_now_iso()
            )

            reason = str(
                row.get(
                    "reason",
                    row.get(
                        "message",
                        "Décision du Brain.",
                    ),
                )
            )

            events.append(
                self._event(
                    source="brain",
                    event_type=(
                        "brain.decision."
                        + decision.lower()
                    ),
                    occurred_at=occurred_at,
                    severity="INFO",
                    title=(
                        f"Décision Brain : {decision}"
                    ),
                    message=reason,
                    payload=row,
                )
            )

        return events

    def _manual_commands(
        self,
        limit: int,
    ) -> list[dict[str, Any]]:
        memory = self._memory()

        rows = self._call_list_method(
            memory,
            (
                "recent_manual_commands",
                "get_recent_manual_commands",
                "list_recent_manual_commands",
            ),
            limit,
        )

        events: list[dict[str, Any]] = []

        for row in rows:
            command_type = str(
                row.get(
                    "command_type",
                    row.get(
                        "type",
                        "UNKNOWN",
                    ),
                )
            )

            status = str(
                row.get(
                    "status",
                    "UNKNOWN",
                )
            )

            occurred_at = (
                row.get("updated_at")
                or row.get("finished_at")
                or row.get("created_at")
                or row.get("requested_at")
                or utc_now_iso()
            )

            severity = "INFO"

            if status.upper() in {
                "FAILED",
                "REFUSED",
                "EXPIRED",
            }:
                severity = "WARNING"

            message = str(
                row.get(
                    "reason",
                    row.get(
                        "message",
                        (
                            f"Commande {command_type} "
                            f"— état {status}."
                        ),
                    ),
                )
            )

            events.append(
                self._event(
                    source="manual_command",
                    event_type=(
                        "manual."
                        + command_type.lower()
                        + "."
                        + status.lower()
                    ),
                    occurred_at=occurred_at,
                    severity=severity,
                    title=(
                        f"Commande manuelle "
                        f"{command_type} : {status}"
                    ),
                    message=message,
                    payload=row,
                )
            )

        return events

    def _flight_recorder_events(
        self,
        limit: int,
    ) -> list[dict[str, Any]]:
        try:
            result = self.flight_recorder.status(
                limit=min(
                    max(limit * 4, 30),
                    300,
                ),
                errors_only=False,
                include_controller=False,
            )
        except Exception:
            return []

        snapshots = self._list(
            self._mapping(
                result
            ).get("snapshots")
        )

        events: list[dict[str, Any]] = []

        previous_summary: dict[str, Any] | None = None

        watched_fields = {
            "state": "État du Controller",
            "mode": "Mode GeoCooling",
            "pump_running": "Circulateur",
            "valve_open": "Vanne",
            "driver_connected": "Connexion Driver",
            "device_online": "ESP32",
            "device_ready": "Disponibilité matériel",
            "heartbeat_fresh": "Heartbeat ESP32",
            "brain_decision": "Décision Brain",
            "safety_safe": "Sécurité thermique",
            "safety_level": "Niveau de sécurité",
            "manual_command_active": (
                "Commande manuelle active"
            ),
        }

        for snapshot in snapshots:
            if not isinstance(
                snapshot,
                dict,
            ):
                continue

            occurred_at = snapshot.get(
                "captured_at",
                utc_now_iso(),
            )

            if not snapshot.get(
                "success",
                False,
            ):
                events.append(
                    self._event(
                        source="flight_recorder",
                        event_type=(
                            "flight_recorder.capture_error"
                        ),
                        occurred_at=occurred_at,
                        severity="ERROR",
                        title=(
                            "Erreur de capture "
                            "du Flight Recorder"
                        ),
                        message=str(
                            snapshot.get(
                                "error",
                                "Erreur inconnue.",
                            )
                        ),
                        payload=snapshot,
                    )
                )

                continue

            summary = self._mapping(
                snapshot.get("summary")
            )

            if previous_summary is None:
                previous_summary = summary
                continue

            for field, label in watched_fields.items():
                old_value = previous_summary.get(
                    field
                )

                new_value = summary.get(
                    field
                )

                if old_value == new_value:
                    continue

                severity = "INFO"

                if field in {
                    "driver_connected",
                    "device_online",
                    "device_ready",
                    "heartbeat_fresh",
                    "safety_safe",
                } and new_value is False:
                    severity = "WARNING"

                if (
                    field == "safety_level"
                    and str(
                        new_value
                    ).lower()
                    in {
                        "critical",
                        "danger",
                        "error",
                        "unsafe",
                    }
                ):
                    severity = "CRITICAL"

                events.append(
                    self._event(
                        source="flight_recorder",
                        event_type=(
                            "state_change."
                            + field
                        ),
                        occurred_at=occurred_at,
                        severity=severity,
                        title=(
                            f"{label} modifié"
                        ),
                        message=(
                            f"{label} : "
                            f"{old_value!r} → "
                            f"{new_value!r}"
                        ),
                        payload={
                            "field": field,
                            "old": old_value,
                            "new": new_value,
                            "sequence": snapshot.get(
                                "sequence"
                            ),
                        },
                    )
                )

            previous_summary = summary

        return events

    def _commissioning_events(
        self,
    ) -> list[dict[str, Any]]:
        try:
            status = (
                self.commissioning_test_manager.status()
            )
        except Exception:
            return []

        if not isinstance(
            status,
            dict,
        ):
            return []

        events: list[dict[str, Any]] = []

        active_test = status.get(
            "active_test"
        )

        if isinstance(
            active_test,
            dict,
        ):
            events.append(
                self._event(
                    source="commissioning",
                    event_type=(
                        "commissioning.test.active"
                    ),
                    occurred_at=active_test.get(
                        "started_at",
                        utc_now_iso(),
                    ),
                    severity="WARNING",
                    title=(
                        "Test de commissioning actif"
                    ),
                    message=str(
                        active_test.get(
                            "message",
                            "Test en cours.",
                        )
                    ),
                    payload=active_test,
                )
            )

        last_test = status.get(
            "last_test"
        )

        if isinstance(
            last_test,
            dict,
        ):
            result = str(
                last_test.get(
                    "result",
                    "UNKNOWN",
                )
            ).upper()

            severity = "INFO"

            if result in {
                "FAILED",
                "COMPLETED_WITH_WARNINGS",
            }:
                severity = "WARNING"

            if result == "CANCELLED":
                severity = "INFO"

            events.append(
                self._event(
                    source="commissioning",
                    event_type=(
                        "commissioning.test."
                        + result.lower()
                    ),
                    occurred_at=(
                        last_test.get(
                            "finished_at"
                        )
                        or last_test.get(
                            "started_at"
                        )
                        or utc_now_iso()
                    ),
                    severity=severity,
                    title=(
                        "Test de commissioning : "
                        f"{result}"
                    ),
                    message=str(
                        last_test.get(
                            "message",
                            "Test terminé.",
                        )
                    ),
                    payload=last_test,
                )
            )

        return events

    @staticmethod
    def _deduplicate(
        events: list[dict[str, Any]],
    ) -> list[dict[str, Any]]:
        unique: dict[
            str,
            dict[str, Any]
        ] = {}

        for event in events:
            event_id = str(
                event.get("id")
            )

            unique[event_id] = event

        return list(
            unique.values()
        )

    @staticmethod
    def _filter_events(
        events: list[dict[str, Any]],
        *,
        source: str | None,
        severity: str | None,
        event_type: str | None,
    ) -> list[dict[str, Any]]:
        filtered = events

        if source:
            normalized_source = (
                source.strip().lower()
            )

            filtered = [
                item
                for item in filtered
                if str(
                    item.get("source", "")
                ).lower()
                == normalized_source
            ]

        if severity:
            normalized_severity = (
                severity.strip().upper()
            )

            filtered = [
                item
                for item in filtered
                if str(
                    item.get("severity", "")
                ).upper()
                == normalized_severity
            ]

        if event_type:
            normalized_type = (
                event_type.strip().lower()
            )

            filtered = [
                item
                for item in filtered
                if normalized_type
                in str(
                    item.get("type", "")
                ).lower()
            ]

        return filtered

    def status(
        self,
        *,
        limit: int = 100,
        source: str | None = None,
        severity: str | None = None,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        normalized_limit = max(
            1,
            min(
                500,
                int(limit),
            ),
        )

        collection_limit = min(
            500,
            max(
                normalized_limit * 2,
                100,
            ),
        )

        events: list[dict[str, Any]] = []

        events.extend(
            self._memory_events(
                collection_limit
            )
        )

        events.extend(
            self._brain_decisions(
                collection_limit
            )
        )

        events.extend(
            self._manual_commands(
                collection_limit
            )
        )

        events.extend(
            self._flight_recorder_events(
                collection_limit
            )
        )

        events.extend(
            self._commissioning_events()
        )

        events = self._deduplicate(
            events
        )

        events = self._filter_events(
            events,
            source=source,
            severity=severity,
            event_type=event_type,
        )

        events.sort(
            key=lambda item: (
                parse_datetime(
                    item.get(
                        "occurred_at"
                    )
                )
                or datetime.min.replace(
                    tzinfo=timezone.utc
                )
            ),
            reverse=True,
        )

        returned_events = copy.deepcopy(
            events[:normalized_limit]
        )

        severity_counts = {
            "DEBUG": 0,
            "INFO": 0,
            "WARNING": 0,
            "ERROR": 0,
            "CRITICAL": 0,
        }

        source_counts: dict[
            str,
            int
        ] = {}

        for event in events:
            event_severity = str(
                event.get(
                    "severity",
                    "INFO",
                )
            ).upper()

            severity_counts[
                event_severity
            ] = (
                severity_counts.get(
                    event_severity,
                    0,
                )
                + 1
            )

            event_source = str(
                event.get(
                    "source",
                    "unknown",
                )
            )

            source_counts[
                event_source
            ] = (
                source_counts.get(
                    event_source,
                    0,
                )
                + 1
            )

        return {
            "component": "geocooling",
            "view": "event_timeline",
            "generated_at": utc_now_iso(),
            "read_only": True,
            "filters": {
                "limit": normalized_limit,
                "source": source,
                "severity": severity,
                "event_type": event_type,
            },
            "summary": {
                "total_available": len(
                    events
                ),
                "returned": len(
                    returned_events
                ),
                "severity_counts": (
                    severity_counts
                ),
                "source_counts": source_counts,
            },
            "events": returned_events,
        }

    def latest(
        self,
    ) -> dict[str, Any]:
        timeline = self.status(
            limit=1
        )

        events = timeline.get(
            "events",
            [],
        )

        return {
            "component": "geocooling",
            "view": "event_timeline_latest",
            "generated_at": utc_now_iso(),
            "read_only": True,
            "event": (
                events[0]
                if events
                else None
            ),
        }


    # PATCH C013.2R1 — Event Timeline Consumer
    @staticmethod
    def _c0132_json_safe(value):
        """Convertit récursivement une valeur en structure JSON-safe."""

        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            return value

        if isinstance(value, dict):
            return {
                str(key): GeoCoolingEventTimeline._c0132_json_safe(item)
                for key, item in value.items()
            }

        if isinstance(value, (list, tuple, set)):
            return [
                GeoCoolingEventTimeline._c0132_json_safe(item)
                for item in value
            ]

        isoformat = getattr(value, "isoformat", None)

        if callable(isoformat):
            try:
                return isoformat()
            except Exception:
                pass

        return repr(value)

    def record_bus_event(
        self,
        event_type,
        event,
    ):
        """Ajoute un événement du bus à la chronologie dédiée."""

        import threading
        from collections import deque
        from datetime import datetime, timezone

        if not hasattr(self, "_c0132_bus_event_lock"):
            self._c0132_bus_event_lock = threading.RLock()

        if not hasattr(self, "_c0132_bus_events"):
            self._c0132_bus_events = deque(maxlen=1000)

        if not hasattr(self, "_c0132_bus_metrics"):
            self._c0132_bus_metrics = {
                "received_count": 0,
                "error_count": 0,
                "last_received_at": None,
                "last_event_type": None,
            }

        received_at = datetime.now(
            timezone.utc
        ).isoformat()

        entry = {
            "event_type": str(event_type),
            "event": self._c0132_json_safe(event),
            "received_at": received_at,
        }

        with self._c0132_bus_event_lock:
            self._c0132_bus_events.append(entry)

            self._c0132_bus_metrics[
                "received_count"
            ] += 1

            self._c0132_bus_metrics[
                "last_received_at"
            ] = received_at

            self._c0132_bus_metrics[
                "last_event_type"
            ] = str(event_type)

        return entry

    def bus_events_history(
        self,
        limit=100,
        event_type=None,
    ):
        """Retourne la chronologie des événements du bus."""

        normalized_limit = max(
            0,
            min(int(limit), 1000),
        )

        events = list(
            getattr(
                self,
                "_c0132_bus_events",
                (),
            )
        )

        if event_type is not None:
            expected = str(event_type)

            events = [
                event
                for event in events
                if event.get("event_type") == expected
            ]

        if normalized_limit == 0:
            return []

        return events[-normalized_limit:]

    def bus_events_status(self):
        """Retourne l'état du consumer Timeline."""

        events = getattr(
            self,
            "_c0132_bus_events",
            (),
        )

        metrics = dict(
            getattr(
                self,
                "_c0132_bus_metrics",
                {
                    "received_count": 0,
                    "error_count": 0,
                    "last_received_at": None,
                    "last_event_type": None,
                },
            )
        )

        counts_by_type = {}

        for event in events:
            event_type = event.get(
                "event_type",
                "unknown",
            )

            counts_by_type[event_type] = (
                counts_by_type.get(event_type, 0)
                + 1
            )

        return {
            "overall": "OK",
            "component": "event_timeline_consumer",
            "patch_version": "C013.2R1",
            "running": True,
            "event_count": len(events),
            "capacity": 1000,
            "events_by_type": dict(
                sorted(counts_by_type.items())
            ),
            "metrics": metrics,
        }
