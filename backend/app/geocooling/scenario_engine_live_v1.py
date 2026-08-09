"""
GeoCooling RC2.1B — live passive Scenario Engine service.

The service:
1. builds the live DecisionContext through the existing read-only aggregator;
2. evaluates all scenarios through the pure ScenarioEngine;
3. returns both payloads and a trace.

It never sends a hardware command, never publishes MQTT, never mutates the
database and never activates the selected scenario.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, Mapping

from app.geocooling.decision_context_live_v1 import (
    LiveDecisionContextService,
)
from app.geocooling.scenario_engine_v1 import (
    ScenarioDecision,
    ScenarioEngine,
    ScenarioWeights,
)


class LiveScenarioEngineService:
    def __init__(
        self,
        *,
        context_service: LiveDecisionContextService | None = None,
        engine: ScenarioEngine | None = None,
    ) -> None:
        self.context_service = (
            context_service
            or LiveDecisionContextService()
        )
        self.engine = engine or ScenarioEngine()

    def evaluate_live(
        self,
        *,
        configuration: Mapping[str, Any] | None = None,
        weights: ScenarioWeights | None = None,
    ) -> dict[str, Any]:
        context = self.context_service.build_live_context(
            configuration=configuration,
        )

        engine = (
            ScenarioEngine(weights=weights)
            if weights is not None
            else self.engine
        )

        decision: ScenarioDecision = engine.evaluate(context)

        return {
            "schema": "geocooling.rc21b.live-scenario-evaluation.v1",
            "generated_at": datetime.now(timezone.utc).isoformat(),
            "mode": "passive",
            "context": context,
            "scenario_decision": decision.as_dict(),
            "activation": {
                "selected_scenario_activated": False,
                "controller_called": False,
                "hardware_called": False,
            },
            "safety": {
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
                "outbound_http_methods": ["GET"],
            },
        }

    def health(self) -> dict[str, Any]:
        sources = self.context_service.source_status()

        available = sum(
            1
            for item in sources["sources"].values()
            if item["available"]
        )
        total = len(sources["sources"])

        return {
            "schema": "geocooling.rc21b.live-scenario-health.v1",
            "ready": available > 0,
            "available_sources": available,
            "total_sources": total,
            "sources": sources["sources"],
            "passive": True,
            "hardware_write": False,
        }
