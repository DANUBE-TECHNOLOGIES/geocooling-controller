"""
C013.3R1 — Métriques temps réel du GeoCoolingEventBus.
"""

from __future__ import annotations

import threading
import time
from collections import Counter, deque
from datetime import datetime, timezone
from typing import Any


class GeoCoolingRealtimeMetrics:
    """Agrège en mémoire les événements reçus depuis le bus."""

    PATCH_VERSION = "C013.3R1"
    SUBSCRIPTION_ID = "c0133-realtime-metrics"

    def __init__(
        self,
        *,
        subscription_manager: Any,
        retention_seconds: int = 3600,
        max_events: int = 10000,
    ) -> None:
        self.subscription_manager = subscription_manager
        self.retention_seconds = max(
            60,
            int(retention_seconds),
        )
        self.max_events = max(
            100,
            int(max_events),
        )

        self._lock = threading.RLock()
        self._started_monotonic = time.monotonic()
        self._started_at = self._utc_now()

        self._events: deque[dict[str, Any]] = deque(
            maxlen=self.max_events
        )

        self._events_by_type: Counter[str] = Counter()
        self._events_by_source: Counter[str] = Counter()
        self._events_by_level: Counter[str] = Counter()

        self._received_count = 0
        self._error_count = 0
        self._last_event_at: str | None = None
        self._last_event_type: str | None = None

        self._subscription_id = (
            self.subscription_manager.subscribe(
                "*",
                self._consume,
                subscription_id=self.SUBSCRIPTION_ID,
            )
        )

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _extract(
        event: Any,
        key: str,
        default: Any = None,
    ) -> Any:
        if isinstance(event, dict):
            return event.get(key, default)

        return getattr(event, key, default)

    def _purge_locked(
        self,
        now_monotonic: float,
    ) -> None:
        cutoff = (
            now_monotonic
            - self.retention_seconds
        )

        while self._events:
            oldest = self._events[0]

            if oldest["monotonic"] >= cutoff:
                break

            self._events.popleft()

    def _consume(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        now_monotonic = time.monotonic()
        received_at = self._utc_now()

        normalized_type = str(
            event_type or "unknown"
        )

        source = self._extract(
            event,
            "source",
            "unknown",
        )

        level = self._extract(
            event,
            "level",
            self._extract(
                event,
                "severity",
                "unknown",
            ),
        )

        normalized_source = str(
            source or "unknown"
        )

        normalized_level = str(
            level or "unknown"
        ).upper()

        try:
            with self._lock:
                self._received_count += 1
                self._last_event_at = received_at
                self._last_event_type = normalized_type

                self._events_by_type[
                    normalized_type
                ] += 1

                self._events_by_source[
                    normalized_source
                ] += 1

                self._events_by_level[
                    normalized_level
                ] += 1

                self._events.append(
                    {
                        "monotonic": now_monotonic,
                        "received_at": received_at,
                        "event_type": normalized_type,
                        "source": normalized_source,
                        "level": normalized_level,
                    }
                )

                self._purge_locked(
                    now_monotonic
                )

        except Exception:
            with self._lock:
                self._error_count += 1
            raise

    def _window_count_locked(
        self,
        *,
        now_monotonic: float,
        seconds: int,
    ) -> int:
        cutoff = now_monotonic - seconds

        return sum(
            1
            for event in self._events
            if event["monotonic"] >= cutoff
        )

    def status(self) -> dict[str, Any]:
        now_monotonic = time.monotonic()

        with self._lock:
            self._purge_locked(
                now_monotonic
            )

            count_1m = self._window_count_locked(
                now_monotonic=now_monotonic,
                seconds=60,
            )

            count_5m = self._window_count_locked(
                now_monotonic=now_monotonic,
                seconds=300,
            )

            count_15m = self._window_count_locked(
                now_monotonic=now_monotonic,
                seconds=900,
            )

            uptime_seconds = max(
                0.0,
                now_monotonic
                - self._started_monotonic,
            )

            return {
                "overall": "OK",
                "component": "geocooling_realtime_metrics",
                "patch_version": self.PATCH_VERSION,
                "running": True,
                "subscription_id":
                    self._subscription_id,
                "started_at": self._started_at,
                "uptime_seconds": round(
                    uptime_seconds,
                    3,
                ),
                "retention_seconds":
                    self.retention_seconds,
                "buffer_capacity":
                    self.max_events,
                "buffer_size":
                    len(self._events),
                "metrics": {
                    "received_count":
                        self._received_count,
                    "error_count":
                        self._error_count,
                    "last_event_at":
                        self._last_event_at,
                    "last_event_type":
                        self._last_event_type,
                    "events_last_1m":
                        count_1m,
                    "events_last_5m":
                        count_5m,
                    "events_last_15m":
                        count_15m,
                    "events_per_minute_1m":
                        float(count_1m),
                    "events_per_minute_5m":
                        round(count_5m / 5, 3),
                    "events_per_minute_15m":
                        round(count_15m / 15, 3),
                },
                "events_by_type": dict(
                    self._events_by_type.most_common()
                ),
                "events_by_source": dict(
                    self._events_by_source.most_common()
                ),
                "events_by_level": dict(
                    self._events_by_level.most_common()
                ),
            }

    def recent(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        normalized_limit = max(
            1,
            min(int(limit), 1000),
        )

        with self._lock:
            events = list(self._events)

        if event_type is not None:
            expected = str(event_type)

            events = [
                event
                for event in events
                if event["event_type"] == expected
            ]

        cleaned = [
            {
                key: value
                for key, value in event.items()
                if key != "monotonic"
            }
            for event in events[-normalized_limit:]
        ]

        return {
            "overall": "OK",
            "component":
                "geocooling_realtime_metrics",
            "limit": normalized_limit,
            "event_type": event_type,
            "count": len(cleaned),
            "events": cleaned,
        }
