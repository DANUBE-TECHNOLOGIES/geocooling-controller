"""
C013.1+C013.2R1 — Consumers du GeoCoolingEventBus.
"""

from __future__ import annotations

from typing import Any


class GeoCoolingEventConsumers:
    """Connecte GeoCoolingFlightRecorder et GeoCoolingEventTimeline au bus."""

    PATCH_VERSION = "C013.1+C013.2R1"

    def __init__(
        self,
        *,
        subscription_manager: Any,
        flight_recorder: Any,
        event_timeline: Any,
    ) -> None:
        self.subscription_manager = subscription_manager
        self.flight_recorder = flight_recorder
        self.event_timeline = event_timeline

        self._subscription_ids: list[str] = []

        self._metrics = {
            "flight_delivery_count": 0,
            "timeline_delivery_count": 0,
            "flight_error_count": 0,
            "timeline_error_count": 0,
        }

        self._install()

    def _flight_callback(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        try:
            self.flight_recorder.record_bus_event(
                event_type,
                event,
            )

            self._metrics[
                "flight_delivery_count"
            ] += 1

        except Exception:
            self._metrics[
                "flight_error_count"
            ] += 1

            raise

    def _timeline_callback(
        self,
        event_type: str,
        event: Any,
    ) -> None:
        try:
            self.event_timeline.record_bus_event(
                event_type,
                event,
            )

            self._metrics[
                "timeline_delivery_count"
            ] += 1

        except Exception:
            self._metrics[
                "timeline_error_count"
            ] += 1

            raise

    def _install(self) -> None:
        self._subscription_ids.append(
            self.subscription_manager.subscribe(
                "*",
                self._flight_callback,
                subscription_id=(
                    "c0131-flight-recorder-consumer"
                ),
            )
        )

        self._subscription_ids.append(
            self.subscription_manager.subscribe(
                "*",
                self._timeline_callback,
                subscription_id=(
                    "c0132-event-timeline-consumer"
                ),
            )
        )

    def status(self) -> dict[str, Any]:
        return {
            "overall": "OK",
            "component": "geocooling_event_consumers",
            "patch_version": self.PATCH_VERSION,
            "running": True,
            "subscription_ids": list(
                self._subscription_ids
            ),
            "subscription_count": len(
                self._subscription_ids
            ),
            "metrics": dict(self._metrics),
            "flight_recorder":
                self.flight_recorder.bus_events_status(),
            "event_timeline":
                self.event_timeline.bus_events_status(),
        }

    def history(
        self,
        *,
        limit: int = 100,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        return {
            "overall": "OK",
            "limit": limit,
            "event_type": event_type,
            "flight_recorder":
                self.flight_recorder.bus_events_history(
                    limit=limit,
                ),
            "event_timeline":
                self.event_timeline.bus_events_history(
                    limit=limit,
                    event_type=event_type,
                ),
        }
