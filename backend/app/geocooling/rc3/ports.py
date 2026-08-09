"""
GeoCooling RC3.0 — dependency ports.

Protocols define the stable boundaries between the decision pipeline and the
existing implementation. No concrete service is imported here.
"""

from __future__ import annotations

from typing import Any, Mapping, Protocol, runtime_checkable

from app.geocooling.rc3.contracts import (
    DecisionInput,
    DecisionOutput,
    ScenarioScore,
)


@runtime_checkable
class ContextProvider(Protocol):
    def build_context(self) -> DecisionInput:
        ...


@runtime_checkable
class ScenarioGenerator(Protocol):
    def generate(self, decision_input: DecisionInput) -> tuple[str, ...]:
        ...


@runtime_checkable
class ScenarioEvaluator(Protocol):
    def evaluate(
        self,
        decision_input: DecisionInput,
        scenario: str,
    ) -> ScenarioScore:
        ...


@runtime_checkable
class ScenarioRanker(Protocol):
    def rank(
        self,
        scores: tuple[ScenarioScore, ...],
    ) -> tuple[ScenarioScore, ...]:
        ...


@runtime_checkable
class DecisionExplainer(Protocol):
    def explain(
        self,
        decision_input: DecisionInput,
        ranked_scores: tuple[ScenarioScore, ...],
    ) -> tuple[str, ...]:
        ...


@runtime_checkable
class SafetyPolicy(Protocol):
    def authorize(
        self,
        decision_input: DecisionInput,
        ranked_scores: tuple[ScenarioScore, ...],
    ) -> bool:
        ...


@runtime_checkable
class DecisionSink(Protocol):
    def publish(self, decision: DecisionOutput) -> None:
        ...


@runtime_checkable
class DecisionObserver(Protocol):
    def observe(
        self,
        decision_input: DecisionInput,
        decision_output: DecisionOutput,
    ) -> None:
        ...


@runtime_checkable
class LegacyContextAdapter(Protocol):
    def from_payload(
        self,
        payload: Mapping[str, Any],
    ) -> DecisionInput:
        ...
