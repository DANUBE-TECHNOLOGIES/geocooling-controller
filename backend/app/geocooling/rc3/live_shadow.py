"""
GeoCooling RC3.2 — live shadow runner.

This service reads the existing live Decision Context and live Scenario Engine,
then feeds both payloads into the RC3 shadow comparison service.

It remains strictly passive:
- GET only toward local APIs;
- no controller authorization;
- no hardware write;
- no MQTT publication;
- no database mutation.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping
from urllib.request import Request, urlopen
from urllib.error import URLError, HTTPError
import json
import os

from app.geocooling.rc3.shadow import ShadowDecisionService


class LocalGetOnlyClient:
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
                "5",
            )
        )

    def get_json(
        self,
        route: str,
    ) -> Mapping[str, Any]:
        request = Request(
            self.base_url + route,
            method="GET",
            headers={
                "Accept": "application/json",
                "User-Agent": "GeoCooling-RC32/1.0",
            },
        )

        with urlopen(
            request,
            timeout=self.timeout_seconds,
        ) as response:
            payload = json.loads(
                response.read().decode("utf-8")
            )

        if not isinstance(payload, Mapping):
            raise TypeError(
                f"JSON root for {route} must be an object"
            )

        return payload


class LiveShadowRunner:
    def __init__(
        self,
        *,
        client: LocalGetOnlyClient | None = None,
        shadow_service: ShadowDecisionService | None = None,
    ) -> None:
        self.client = client or LocalGetOnlyClient()
        self.shadow_service = (
            shadow_service
            or ShadowDecisionService()
        )

    def run(self) -> dict[str, Any]:
        context_payload = self.client.get_json(
            "/geocooling/decision-context/live"
        )
        scenario_live = self.client.get_json(
            "/geocooling/scenario-engine/live"
        )

        scenario_payload = scenario_live.get(
            "scenario_decision"
        )

        if not isinstance(
            scenario_payload,
            Mapping,
        ):
            raise TypeError(
                "scenario_decision missing from live scenario payload"
            )

        comparison = self.shadow_service.compare(
            context_payload=context_payload,
            scenario_payload=scenario_payload,
        ).as_dict()

        return {
            "schema": "geocooling.rc32.live-shadow-run.v1",
            "generated_at": datetime.now(
                timezone.utc
            ).isoformat(),
            "mode": "SHADOW",
            "comparison": comparison,
            "sources": {
                "context_route": (
                    "/geocooling/decision-context/live"
                ),
                "scenario_route": (
                    "/geocooling/scenario-engine/live"
                ),
            },
            "activation": {
                "controller_authorized": False,
                "controller_called": False,
                "hardware_called": False,
                "selected_scenario_activated": False,
            },
            "safety": {
                "outbound_http_methods": ["GET"],
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }

    def health(self) -> dict[str, Any]:
        checks = {}

        for name, route in {
            "context": "/geocooling/decision-context/live",
            "scenario": "/geocooling/scenario-engine/live",
        }.items():
            try:
                self.client.get_json(route)
                checks[name] = {
                    "available": True,
                    "route": route,
                    "error": None,
                }
            except (
                URLError,
                HTTPError,
                TimeoutError,
                ValueError,
                TypeError,
                RuntimeError,
            ) as exc:
                checks[name] = {
                    "available": False,
                    "route": route,
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }
            except Exception as exc:
                checks[name] = {
                    "available": False,
                    "route": route,
                    "error": (
                        f"{type(exc).__name__}: {exc}"
                    ),
                }

        ready = all(
            item["available"]
            for item in checks.values()
        )

        return {
            "schema": "geocooling.rc32.live-shadow-health.v1",
            "ready": ready,
            "checks": checks,
            "mode": "SHADOW",
            "controller_authorized": False,
            "hardware_write": False,
        }
