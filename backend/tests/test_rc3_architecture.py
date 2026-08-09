from app.geocooling.rc3.contracts import (
    DecisionAction,
    DecisionInput,
    DecisionMode,
)
from app.geocooling.rc3.defaults import (
    DefaultDecisionExplainer,
    DefaultScenarioGenerator,
    DescendingScenarioRanker,
    PassiveSafetyPolicy,
    PassiveScenarioEvaluator,
    StaticContextProvider,
)
from app.geocooling.rc3.pipeline import DecisionPipeline


def test_rc3_pipeline_is_passive_by_default() -> None:
    pipeline = DecisionPipeline(
        context_provider=StaticContextProvider(
            DecisionInput.empty(
                mode=DecisionMode.PASSIVE,
            )
        ),
        scenario_generator=DefaultScenarioGenerator(),
        scenario_evaluator=PassiveScenarioEvaluator(),
        scenario_ranker=DescendingScenarioRanker(),
        decision_explainer=DefaultDecisionExplainer(),
        safety_policy=PassiveSafetyPolicy(),
    )

    result = pipeline.run()

    assert result.selected_scenario == "WAIT"
    assert result.action is DecisionAction.WAIT
    assert result.controller_authorized is False


def test_rc3_contract_is_versioned() -> None:
    decision_input = DecisionInput.empty()

    assert decision_input.schema == (
        "geocooling.rc3.decision-input.v1"
    )
