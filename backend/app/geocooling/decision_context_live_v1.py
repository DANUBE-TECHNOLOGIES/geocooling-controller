"""
GeoCooling RC1.7C — live passive DecisionContext aggregation.

This module only performs HTTP GET requests against the local GeoCooling API.
It does not call any POST/PUT/PATCH/DELETE route, does not write to hardware,
does not publish MQTT messages and does not persist data.
"""

from __future__ import annotations

import json
import os
from dataclasses import dataclass
from typing import Any, Mapping
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

from app.geocooling.decision_context_builder_v1 import (
    PassiveDecisionContextBuilder,
)


@dataclass(frozen=True, slots=True)
class ReadResult:
    source: str
    route: str | None
    available: bool
    payload: Mapping[str, Any] | None
    error: str | None = None

    def as_dict(self) -> dict[str, Any]:
        return {
            "source": self.source,
            "route": self.route,
            "available": self.available,
            "error": self.error,
        }


DEFAULT_SOURCE_ROUTES: dict[str, tuple[str, ...]] = {
    "thermal": (
        "/geocooling/thermal",
        "/geocooling/dashboard",
        "/geocooling/status",
    ),
    "weather": (
        "/geocooling/weather",
        "/building/weather",
        "/geocooling/forecast",
    ),
    "prediction": (
        "/geocooling/prediction",
        "/geocooling/brain/forecast",
    ),
    "learning": (
        "/geocooling/industrial-platform/thermal-model-learning",
        "/geocooling/brain-v2/learning/status",
    ),
    "historian": (
        "/geocooling/historian/status",
        "/geocooling/historian/latest",
        "/geocooling/history",
    ),
    "hardware": (
        "/geocooling/manual/hardware/status",
        "/geocooling/industrial-platform/hardware-readiness",
        "/geocooling/relay/status",
    ),
    "runtime": (
        "/geocooling/runtime",
        "/geocooling/status",
    ),
}


class LocalReadOnlyApiClient:
    def __init__(
        self,
        *,
        base_url: str | None = None,
        timeout_seconds: float | None = None,
    ) -> None:
        self.base_url = (
            base_url
            or os.getenv(
                "GEOCOOLING_INTERNAL_API_BASE_URL",
                "http://127.0.0.1:8000",
            )
        ).rstrip("/")
        self.timeout_seconds = float(
            timeout_seconds
            or os.getenv(
                "GEOCOOLING_INTERNAL_API_TIMEOUT_SECONDS",
                "3",
            )
        )

    def get_json(self, route: str) -> Mapping[str, Any]:
        request = Request(
            self.base_url + route,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "GeoCooling-RC17C/1.0",
            },
        )

        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            if response.status < 200 or response.status >= 300:
                raise RuntimeError(
                    f"unexpected HTTP status {response.status}"
                )

            payload = json.loads(
                response.read().decode("utf-8")
            )

        if not isinstance(payload, Mapping):
            return {"value": payload}

        return payload


class LiveDecisionContextService:
    def __init__(
        self,
        *,
        client: LocalReadOnlyApiClient | None = None,
        builder: PassiveDecisionContextBuilder | None = None,
        routes: Mapping[str, tuple[str, ...]] | None = None,
    ) -> None:
        self.client = client or LocalReadOnlyApiClient()
        self.builder = builder or PassiveDecisionContextBuilder()
        self.routes = dict(routes or DEFAULT_SOURCE_ROUTES)

    def _read_source(self, source: str) -> ReadResult:
        candidates = self.routes.get(source, ())
        errors: list[str] = []

        for route in candidates:
            try:
                payload = self.client.get_json(route)

                return ReadResult(
                    source=source,
                    route=route,
                    available=True,
                    payload=payload,
                )
            except HTTPError as exc:
                errors.append(
                    f"{route}: HTTP {exc.code}"
                )
            except (URLError, TimeoutError, ValueError, RuntimeError) as exc:
                errors.append(
                    f"{route}: {type(exc).__name__}: {exc}"
                )
            except Exception as exc:
                errors.append(
                    f"{route}: {type(exc).__name__}: {exc}"
                )

        return ReadResult(
            source=source,
            route=None,
            available=False,
            payload=None,
            error="; ".join(errors) if errors else "no route configured",
        )

    def build_live_context(
        self,
        *,
        configuration: Mapping[str, Any] | None = None,
    ) -> dict[str, Any]:
        results = {
            source: self._read_source(source)
            for source in self.routes
        }

        context = self.builder.build(
            thermal=results["thermal"].payload,
            weather=results["weather"].payload,
            prediction=results["prediction"].payload,
            learning=results["learning"].payload,
            historian=results["historian"].payload,
            hardware=results["hardware"].payload,
            runtime=results["runtime"].payload,
            configuration=configuration,
        )

        payload = context.as_dict()
        payload["live_sources"] = {
            source: result.as_dict()
            for source, result in results.items()
        }
        payload["live_mode"] = {
            "read_only": True,
            "http_methods_used": ["GET"],
            "hardware_write": False,
            "mqtt_publish": False,
            "database_write": False,
        }

        return payload

    def source_status(self) -> dict[str, Any]:
        results = {
            source: self._read_source(source)
            for source in self.routes
        }

        return {
            "schema": "geocooling.decision-context-live-sources.v1",
            "read_only": True,
            "sources": {
                source: result.as_dict()
                for source, result in results.items()
            },
        }
