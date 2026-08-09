"""
GeoCooling RC3.0 — safe default components for architecture validation.

These implementations are passive and deterministic.
"""

from __future__ import annotations

from app.geocooling.rc3.contracts import (
    DecisionInput,
    ScenarioScore,
)


class StaticContextProvider:
    def __init__(self, decision_input: DecisionInput) -> None:
        self._decision_input = decision_input

    def build_context(self) -> DecisionInput:
        return self._decision_input


class DefaultScenarioGenerator:
    def generate(
        self,
        decision_input: DecisionInput,
    ) -> tuple[str, ...]:
        return (
            "WAIT",
            "PRECOOL_30",
            "PRECOOL_60",
            "COOL_NOW",
            "SOFT_COOLING",
        )


class PassiveScenarioEvaluator:
    def evaluate(
        self,
        decision_input: DecisionInput,
        scenario: str,
    ) -> ScenarioScore:
        default_scores = {
            "WAIT": 0.80,
            "PRECOOL_30": 0.70,
            "PRECOOL_60": 0.65,
            "COOL_NOW": 0.60,
            "SOFT_COOLING": 0.68,
        }
        total = default_scores.get(scenario, 0.0)

        return ScenarioScore(
            name=scenario,
            total_score=total,
            comfort_score=total,
            safety_score=1.0,
            energy_score=1.0 if scenario == "WAIT" else 0.6,
            stability_score=0.9,
            learning_score=0.5,
            predicted_indoor_temperature_c=None,
            estimated_runtime_minutes=0,
            estimated_energy_kwh=0.0,
            reasons=("RC3 architecture validation score.",),
        )


class DescendingScenarioRanker:
    def rank(
        self,
        scores: tuple[ScenarioScore, ...],
    ) -> tuple[ScenarioScore, ...]:
        return tuple(
            sorted(
                scores,
                key=lambda item: item.total_score,
                reverse=True,
            )
        )


class DefaultDecisionExplainer:
    def explain(
        self,
        decision_input: DecisionInput,
        ranked_scores: tuple[ScenarioScore, ...],
    ) -> tuple[str, ...]:
        if not ranked_scores:
            return ("No scenario available.",)

        return (
            f"Selected {ranked_scores[0].name}.",
            "RC3.0 architecture pipeline is passive.",
        )


class PassiveSafetyPolicy:
    def authorize(
        self,
        decision_input: DecisionInput,
        ranked_scores: tuple[ScenarioScore, ...],
    ) -> bool:
        return False
