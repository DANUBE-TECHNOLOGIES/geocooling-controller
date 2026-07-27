from __future__ import annotations

import fnmatch
import json
import logging
import os
import queue
import threading
import time
from collections import Counter, deque
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text
from sqlalchemy.engine import Engine

from app.events.models import Event, EventPriority

logger = logging.getLogger("sbc.events")
EventHandler = Callable[[Event], None]


class EventBus:
    """Bus d'événements interne, asynchrone, persistant et thread-safe."""

    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self.queue_size = max(100, int(os.getenv("EVENT_BUS_QUEUE_SIZE", "2000")))
        self.history_size = max(50, int(os.getenv("EVENT_BUS_HISTORY_SIZE", "500")))
        self.batch_size = max(1, int(os.getenv("EVENT_BUS_BATCH_SIZE", "50")))
        self.flush_seconds = max(0.1, float(os.getenv("EVENT_BUS_FLUSH_SECONDS", "1")))
        self._queue: queue.Queue[Event] = queue.Queue(maxsize=self.queue_size)
        self._history: deque[dict[str, Any]] = deque(maxlen=self.history_size)
        self._subscribers: dict[str, list[EventHandler]] = {}
        self._lock = threading.RLock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.running = False
        self.started_at: datetime | None = None
        self.last_event_at: datetime | None = None
        self.last_persist_at: datetime | None = None
        self.last_error: str | None = None
        self.published_count = 0
        self.processed_count = 0
        self.persisted_count = 0
        self.dropped_count = 0
        self.handler_error_count = 0
        self.type_counts: Counter[str] = Counter()

    def initialize(self) -> None:
        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS event_bus_events (
                    id BIGSERIAL PRIMARY KEY,
                    event_id UUID NOT NULL UNIQUE,
                    created_at TIMESTAMPTZ NOT NULL,
                    event_type TEXT NOT NULL,
                    source TEXT NOT NULL,
                    priority TEXT NOT NULL,
                    correlation_id TEXT,
                    payload JSONB NOT NULL DEFAULT '{}'::jsonb,
                    persisted_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_event_bus_created_at
                ON event_bus_events (created_at DESC)
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_event_bus_type_created
                ON event_bus_events (event_type, created_at DESC)
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_event_bus_source_created
                ON event_bus_events (source, created_at DESC)
            """))

    def start(self) -> None:
        if self.running:
            return
        self.initialize()
        self._stop.clear()
        self.running = True
        self.started_at = datetime.now(timezone.utc)
        self._thread = threading.Thread(target=self._worker, name="event-bus", daemon=True)
        self._thread.start()

    def stop(self, timeout: float = 5.0) -> None:
        if not self.running:
            return
        self.publish("system.event_bus_stopping", "event_bus", {"pending": self._queue.qsize()})
        deadline = time.monotonic() + max(0.5, timeout)
        while not self._queue.empty() and time.monotonic() < deadline:
            time.sleep(0.05)
        self._stop.set()
        if self._thread:
            self._thread.join(timeout=max(0.5, deadline - time.monotonic()))
        self.running = False

    def subscribe(self, pattern: str, handler: EventHandler) -> None:
        if not pattern or not callable(handler):
            raise ValueError("pattern et handler sont obligatoires")
        with self._lock:
            handlers = self._subscribers.setdefault(pattern, [])
            if handler not in handlers:
                handlers.append(handler)

    def unsubscribe(self, pattern: str, handler: EventHandler) -> None:
        with self._lock:
            handlers = self._subscribers.get(pattern, [])
            if handler in handlers:
                handlers.remove(handler)
            if not handlers:
                self._subscribers.pop(pattern, None)

    def publish(
        self,
        event_type: str,
        source: str,
        payload: dict[str, Any] | None = None,
        priority: EventPriority | str = EventPriority.INFO,
        correlation_id: str | None = None,
    ) -> str:
        if not event_type or not source:
            raise ValueError("event_type et source sont obligatoires")
        if isinstance(priority, str):
            priority = EventPriority(priority.lower())
        event = Event(
            event_type=event_type.strip(),
            source=source.strip(),
            payload=payload or {},
            priority=priority,
            correlation_id=correlation_id,
        )
        self.published_count += 1
        try:
            self._queue.put_nowait(event)
        except queue.Full:
            self.dropped_count += 1
            self.last_error = "File d'événements pleine"
            logger.error("Événement abandonné: %s", event.event_type)
        return event.event_id

    def _worker(self) -> None:
        pending: list[Event] = []
        last_flush = time.monotonic()
        while not self._stop.is_set() or not self._queue.empty() or pending:
            timeout = max(0.05, self.flush_seconds - (time.monotonic() - last_flush))
            try:
                pending.append(self._queue.get(timeout=timeout))
            except queue.Empty:
                pass

            while len(pending) < self.batch_size:
                try:
                    pending.append(self._queue.get_nowait())
                except queue.Empty:
                    break

            should_flush = pending and (
                len(pending) >= self.batch_size
                or time.monotonic() - last_flush >= self.flush_seconds
                or self._stop.is_set()
            )
            if should_flush:
                for event in pending:
                    self._dispatch(event)
                self._persist(pending)
                for _ in pending:
                    self._queue.task_done()
                pending.clear()
                last_flush = time.monotonic()

    def _dispatch(self, event: Event) -> None:
        item = event.to_dict()
        with self._lock:
            self._history.appendleft(item)
            subscribers = [
                handler
                for pattern, handlers in self._subscribers.items()
                if fnmatch.fnmatchcase(event.event_type, pattern)
                for handler in handlers
            ]
        self.processed_count += 1
        self.last_event_at = event.created_at
        self.type_counts[event.event_type] += 1
        for handler in subscribers:
            try:
                handler(event)
            except Exception as exc:
                self.handler_error_count += 1
                self.last_error = f"Handler {handler!r}: {exc}"
                logger.exception("Erreur handler pour %s", event.event_type)

    def _persist(self, events: list[Event]) -> None:
        if not events:
            return
        rows = [
            {
                "event_id": event.event_id,
                "created_at": event.created_at,
                "event_type": event.event_type,
                "source": event.source,
                "priority": event.priority.value,
                "correlation_id": event.correlation_id,
                "payload": json.dumps(event.payload, default=str),
            }
            for event in events
        ]
        try:
            with self.engine.begin() as connection:
                connection.execute(text("""
                    INSERT INTO event_bus_events (
                        event_id, created_at, event_type, source,
                        priority, correlation_id, payload
                    ) VALUES (
                        CAST(:event_id AS UUID), :created_at, :event_type, :source,
                        :priority, :correlation_id, CAST(:payload AS JSONB)
                    )
                    ON CONFLICT (event_id) DO NOTHING
                """), rows)
            self.persisted_count += len(rows)
            self.last_persist_at = datetime.now(timezone.utc)
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception("Persistance Event Bus impossible")

    def recent(
        self,
        limit: int = 50,
        event_type: str | None = None,
        source: str | None = None,
        persisted: bool = True,
    ) -> list[dict[str, Any]]:
        limit = min(max(1, limit), 500)
        if not persisted:
            with self._lock:
                items = list(self._history)
            return [
                item for item in items
                if (not event_type or fnmatch.fnmatchcase(item["event_type"], event_type))
                and (not source or item["source"] == source)
            ][:limit]

        conditions = []
        params: dict[str, Any] = {"limit": limit}
        if event_type:
            conditions.append("event_type LIKE :event_type")
            params["event_type"] = event_type.replace("*", "%")
        if source:
            conditions.append("source = :source")
            params["source"] = source
        where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
        with self.engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT event_id::text, created_at, event_type, source,
                       priority, correlation_id, payload
                FROM event_bus_events
                {where}
                ORDER BY created_at DESC
                LIMIT :limit
            """), params).mappings().all()
        return [
            {
                **dict(row),
                "created_at": row["created_at"].isoformat(),
                "payload": row["payload"] or {},
            }
            for row in rows
        ]

    def event_types(self) -> list[dict[str, Any]]:
        with self.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT event_type, COUNT(*) AS count, MAX(created_at) AS last_seen_at
                FROM event_bus_events
                GROUP BY event_type
                ORDER BY count DESC, event_type
            """)).mappings().all()
        return [
            {
                "event_type": row["event_type"],
                "count": int(row["count"]),
                "last_seen_at": row["last_seen_at"].isoformat(),
            }
            for row in rows
        ]

    def diagnostics(self) -> dict[str, Any]:
        with self._lock:
            subscriber_patterns = {
                pattern: len(handlers) for pattern, handlers in self._subscribers.items()
            }
        return {
            "running": self.running,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "last_event_at": self.last_event_at.isoformat() if self.last_event_at else None,
            "last_persist_at": self.last_persist_at.isoformat() if self.last_persist_at else None,
            "last_error": self.last_error,
            "published_count": self.published_count,
            "processed_count": self.processed_count,
            "persisted_count": self.persisted_count,
            "dropped_count": self.dropped_count,
            "handler_error_count": self.handler_error_count,
            "queue_depth": self._queue.qsize(),
            "queue_size": self.queue_size,
            "history_size": len(self._history),
            "subscriber_patterns": subscriber_patterns,
            "top_event_types": self.type_counts.most_common(10),
        }
