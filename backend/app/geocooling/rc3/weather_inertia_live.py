"""
RC3.5 live service. GET-only data aggregation and passive prediction.
"""

from __future__ import annotations

from typing import Any

from app.geocooling.rc3.live_shadow import LocalGetOnlyClient
from app.geocooling.rc3.weather_inertia_predictor import (
    WeatherInertiaPredictor,
)


class LiveWeatherInertiaPredictionService:
    def __init__(
        self,
        *,
        client: LocalGetOnlyClient | None = None,
        predictor: WeatherInertiaPredictor | None = None,
    ) -> None:
        self.client = client or LocalGetOnlyClient()
        self.predictor = predictor or WeatherInertiaPredictor()

    def predict(self) -> dict[str, Any]:
        context = self.client.get_json(
            "/geocooling/decision-context/live"
        )

        weather = self._weather_payload(context)

        prediction = self.predictor.predict(
            context=context,
            weather=weather,
        )
        prediction["sources"] = {
            "context": "/geocooling/decision-context/live",
            "weather": weather.get("_source_route"),
        }

        return prediction

    def _weather_payload(
        self,
        context: dict[str, Any],
    ) -> dict[str, Any]:
        candidates = (
            "/geocooling/weather",
            "/building/weather",
            "/geocooling/forecast",
        )

        for route in candidates:
            try:
                payload = dict(self.client.get_json(route))
                payload["_source_route"] = route
                return payload
            except Exception:
                continue

        embedded = context.get("weather")

        if isinstance(embedded, dict):
            payload = dict(embedded)
            payload["_source_route"] = "decision-context"
            return payload

        return {
            "_source_route": None,
        }
