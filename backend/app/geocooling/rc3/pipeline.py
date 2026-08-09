"""
GeoCooling RC3.0 — deterministic decision pipeline.

The pipeline is orchestration only. It contains no hardware driver, MQTT
publisher, database client, HTTP client or background task.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone

from app.geocooling.rc3.contracts import (
    DecisionAction,
    DecisionInput,
    DecisionMode,
    DecisionOutput,
    ScenarioScore,
)
from app.geocooling.rc3.ports import (
    ContextProvider,
    DecisionExplainer,
    DecisionObserver,
    SafetyPolicy,
    ScenarioEvaluator,
    ScenarioGenerator,
    ScenarioRanker,
)


@dataclass(slots=True)
class DecisionPipeline:
    context_provider: ContextProvider
    scenario_generator: ScenarioGenerator
    scenario_evaluator: ScenarioEvaluator
    scenario_ranker: ScenarioRanker
    decision_explainer: DecisionExplainer
    safety_policy: SafetyPolicy
    observers: tuple[DecisionObserver, ...] = ()

    def run(self) -> DecisionOutput:
        decision_input = self.context_provider.build_context()

        scenario_names = self.scenario_generator.generate(
            decision_input
        )

        scores = tuple(
            self.scenario_evaluator.evaluate(
                decision_input,
                scenario_name,
            )
            for scenario_name in scenario_names
        )

        ranked = self.scenario_ranker.rank(scores)
        authorized = self.safety_policy.authorize(
            decision_input,
            ranked,
        )

        selected = ranked[0] if ranked else None
        action = self._action_for(
            decision_input,
            selected,
            authorized,
        )
        reasons = self.decision_explainer.explain(
            decision_input,
            ranked,
        )

        confidence = (
            max(0.0, min(1.0, selected.total_score))
            if selected is not None
            else 0.0
        )

        output = DecisionOutput(
            schema="geocooling.rc3.decision-output.v1",
            generated_at=datetime.now(timezone.utc).isoformat(),
            mode=decision_input.mode,
            action=action,
            confidence=confidence,
            selected_scenario=(
                selected.name
                if selected is not None
                else None
            ),
            scenarios=ranked,
            reasons=reasons,
            constraints=decision_input.constraints,
            controller_authorized=(
                authorized
                and decision_input.mode is DecisionMode.ACTIVE
            ),
            metadata={
                "pipeline": "DecisionPipeline",
                "architecture": "RC3.0",
            },
        )

        for observer in self.observers:
            observer.observe(
                decision_input,
                output,
            )

        return output

    @staticmethod
    def _action_for(
        decision_input: DecisionInput,
        selected: ScenarioScore | None,
        authorized: bool,
    ) -> DecisionAction:
        if any(
            violation.blocking
            for violation in decision_input.constraints
        ):
            return DecisionAction.BLOCKED

        if selected is None:
            return DecisionAction.WAIT

        mapping = {
            "WAIT": DecisionAction.WAIT,
            "PRECOOL_30": DecisionAction.PRECOOL,
            "PRECOOL_60": DecisionAction.PRECOOL,
            "COOL_NOW": DecisionAction.START_COOLING,
            "SOFT_COOLING": DecisionAction.HOLD_COOLING,
        }

        action = mapping.get(
            selected.name,
            DecisionAction.WAIT,
        )

        if not authorized and action is not DecisionAction.WAIT:
            return DecisionAction.WAIT

        return action
