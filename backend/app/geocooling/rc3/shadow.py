"""
GeoCooling RC3.1 — shadow pipeline.

It compares the existing Decision Context / Scenario Engine outputs with RC3
contracts. It never authorizes the Controller.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Mapping

from app.geocooling.rc3.adapters import (
    LegacyDecisionContextAdapter,
    LegacyScenarioResultAdapter,
)
from app.geocooling.rc3.contracts import (
    DecisionAction,
    DecisionMode,
    DecisionOutput,
    ScenarioScore,
)


@dataclass(frozen=True, slots=True)
class ShadowComparison:
    rc3_output: DecisionOutput
    legacy_action: str | None
    legacy_selected_scenario: str | None
    action_match: bool
    scenario_match: bool

    def as_dict(self) -> dict[str, Any]:
        return {
            "schema": "geocooling.rc3.shadow-comparison.v1",
            "rc3_output": self.rc3_output.as_dict(),
            "legacy": {
                "action": self.legacy_action,
                "selected_scenario": (
                    self.legacy_selected_scenario
                ),
            },
            "comparison": {
                "action_match": self.action_match,
                "scenario_match": self.scenario_match,
            },
            "safety": {
                "controller_authorized": False,
                "hardware_write": False,
                "mqtt_publish": False,
                "database_write": False,
            },
        }


class ShadowDecisionService:
    def __init__(self) -> None:
        self.context_adapter = (
            LegacyDecisionContextAdapter()
        )
        self.scenario_adapter = (
            LegacyScenarioResultAdapter()
        )

    def compare(
        self,
        *,
        context_payload: Mapping[str, Any],
        scenario_payload: Mapping[str, Any],
    ) -> ShadowComparison:
        decision_input = self.context_adapter.from_payload(
            context_payload,
            mode=DecisionMode.SHADOW,
        )

        scores = self.scenario_adapter.from_payload(
            scenario_payload
        )

        ranked = tuple(
            sorted(
                scores,
                key=lambda item: item.total_score,
                reverse=True,
            )
        )

        selected = ranked[0] if ranked else None

        action = self._action_for(
            selected,
            decision_input.constraints,
        )

        rc3_output = DecisionOutput(
            schema="geocooling.rc3.decision-output.v1",
            generated_at=datetime.now(
                timezone.utc
            ).isoformat(),
            mode=DecisionMode.SHADOW,
            action=action,
            confidence=(
                max(
                    0.0,
                    min(
                        1.0,
                        selected.total_score,
                    ),
                )
                if selected is not None
                else 0.0
            ),
            selected_scenario=(
                selected.name
                if selected is not None
                else None
            ),
            scenarios=ranked,
            reasons=(
                "RC3 shadow mode only.",
                "Controller authorization is disabled.",
            ),
            constraints=decision_input.constraints,
            controller_authorized=False,
            metadata={
                "service": "ShadowDecisionService",
                "context_source_schema": (
                    context_payload.get("schema")
                ),
                "scenario_source_schema": (
                    scenario_payload.get("schema")
                ),
            },
        )

        legacy_recommendation = context_payload.get(
            "recommendation"
        )
        legacy_action = None

        if isinstance(
            legacy_recommendation,
            Mapping,
        ):
            value = legacy_recommendation.get(
                "action"
            )
            legacy_action = (
                str(value)
                if value is not None
                else None
            )

        legacy_selected = scenario_payload.get(
            "selected"
        )
        legacy_selected_scenario = None

        if isinstance(legacy_selected, Mapping):
            value = legacy_selected.get("scenario")
            legacy_selected_scenario = (
                str(value)
                if value is not None
                else None
            )

        return ShadowComparison(
            rc3_output=rc3_output,
            legacy_action=legacy_action,
            legacy_selected_scenario=(
                legacy_selected_scenario
            ),
            action_match=(
                self._normalize_action(
                    legacy_action
                )
                == rc3_output.action
            ),
            scenario_match=(
                legacy_selected_scenario
                == rc3_output.selected_scenario
            ),
        )

    @staticmethod
    def _normalize_action(
        value: str | None,
    ) -> DecisionAction:
        mapping = {
            "WAIT": DecisionAction.WAIT,
            "PRECOOL": DecisionAction.PRECOOL,
            "START_COOLING": (
                DecisionAction.START_COOLING
            ),
            "HOLD_COOLING": (
                DecisionAction.HOLD_COOLING
            ),
            "STOP_COOLING": (
                DecisionAction.STOP_COOLING
            ),
            "BLOCKED": DecisionAction.BLOCKED,
        }

        return mapping.get(
            str(value or "").upper(),
            DecisionAction.WAIT,
        )

    @staticmethod
    def _action_for(
        selected: ScenarioScore | None,
        constraints: tuple[Any, ...],
    ) -> DecisionAction:
        if any(
            getattr(
                constraint,
                "blocking",
                False,
            )
            for constraint in constraints
        ):
            return DecisionAction.BLOCKED

        if selected is None:
            return DecisionAction.WAIT

        mapping = {
            "WAIT": DecisionAction.WAIT,
            "PRECOOL_30": DecisionAction.PRECOOL,
            "PRECOOL_60": DecisionAction.PRECOOL,
            "COOL_NOW": (
                DecisionAction.START_COOLING
            ),
            "SOFT_COOLING": (
                DecisionAction.HOLD_COOLING
            ),
        }

        return mapping.get(
            selected.name,
            DecisionAction.WAIT,
        )
