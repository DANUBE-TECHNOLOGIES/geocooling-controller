from __future__ import annotations

import copy
import logging
import operator
from collections.abc import Callable
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine

from app.rules.models import (
    AutomationRule,
    ConditionOperator,
    ExecutionMode,
    RuleStatus,
)
from app.rules.repository import MemoryRuleRepository, RuleRepository

logger = logging.getLogger("sbc.rules")
ActionHandler = Callable[[dict[str, Any]], dict[str, Any] | None]
_MISSING = object()


class RuleEngineService:
    def __init__(
        self,
        engine: Engine | None = None,
        *,
        repository: RuleRepository | MemoryRuleRepository | None = None,
    ) -> None:
        self.repository = repository or (
            RuleRepository(engine)
            if engine is not None
            else MemoryRuleRepository()
        )
        self._action_handlers: dict[str, ActionHandler] = {}
        self.last_evaluation_at: str | None = None
        self.last_error: str | None = None
        self.evaluation_count = 0

    def initialize(self) -> None:
        self.repository.initialize()

    def register_action(
        self,
        action_name: str,
        handler: ActionHandler,
    ) -> None:
        self._action_handlers[action_name] = handler

    @staticmethod
    def _resolve_path(
        context: dict[str, Any],
        path: str,
    ) -> Any:
        current: Any = context

        for part in path.split("."):
            if isinstance(current, dict) and part in current:
                current = current[part]
            else:
                return _MISSING

        return current

    @staticmethod
    def _compare(
        actual: Any,
        condition_operator: ConditionOperator,
        expected: Any,
    ) -> bool:
        if condition_operator == ConditionOperator.EXISTS:
            return actual is not _MISSING

        if actual is _MISSING:
            return False

        if condition_operator == ConditionOperator.TRUTHY:
            return bool(actual)

        if condition_operator == ConditionOperator.FALSY:
            return not bool(actual)

        operations = {
            ConditionOperator.EQ: operator.eq,
            ConditionOperator.NE: operator.ne,
            ConditionOperator.GT: operator.gt,
            ConditionOperator.GTE: operator.ge,
            ConditionOperator.LT: operator.lt,
            ConditionOperator.LTE: operator.le,
            ConditionOperator.IN: lambda left, right: left in right,
            ConditionOperator.NOT_IN: lambda left, right: left not in right,
        }

        try:
            return bool(
                operations[condition_operator](
                    actual,
                    expected,
                )
            )
        except (TypeError, ValueError, KeyError):
            return False

    def evaluate_rule(
        self,
        rule: AutomationRule,
        context: dict[str, Any],
        *,
        mode: ExecutionMode = ExecutionMode.SIMULATION,
        blocked_resources: set[str] | None = None,
    ) -> dict[str, Any]:
        blocked_resources = blocked_resources or set()
        condition_results: list[dict[str, Any]] = []

        if not rule.enabled:
            return {
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "priority": rule.priority,
                "status": RuleStatus.DISABLED.value,
                "matched": False,
                "conditions": [],
                "actions": [],
                "explanation": {
                    "summary": "Règle désactivée",
                    "passed_conditions": 0,
                    "failed_conditions": 0,
                    "total_conditions": 0,
                },
            }

        for condition in rule.conditions:
            actual = self._resolve_path(context, condition.path)
            passed = self._compare(
                actual,
                condition.operator,
                condition.expected,
            )
            condition_results.append({
                "path": condition.path,
                "label": condition.label or condition.path,
                "operator": condition.operator.value,
                "expected": condition.expected,
                "actual": None if actual is _MISSING else actual,
                "available": actual is not _MISSING,
                "passed": passed,
            })

        matched = all(
            item["passed"]
            for item in condition_results
        )
        actions: list[dict[str, Any]] = []
        status = (
            RuleStatus.MATCHED
            if matched
            else RuleStatus.NOT_MATCHED
        )

        if matched:
            for action in rule.actions:
                resource = action.resource or action.target

                if resource in blocked_resources:
                    status = RuleStatus.BLOCKED
                    actions.append({
                        "action": action.action,
                        "target": action.target,
                        "resource": resource,
                        "status": "blocked",
                        "reason": (
                            "Ressource réservée par "
                            "une règle plus prioritaire"
                        ),
                    })
                    continue

                action_result = {
                    "action": action.action,
                    "target": action.target,
                    "resource": resource,
                    "parameters": copy.deepcopy(
                        action.parameters
                    ),
                    "status": (
                        "simulated"
                        if mode == ExecutionMode.SIMULATION
                        else "planned"
                    ),
                }

                if mode == ExecutionMode.REAL:
                    handler = self._action_handlers.get(
                        action.action
                    )

                    if handler is None:
                        action_result["status"] = "rejected"
                        action_result["reason"] = (
                            "Aucun gestionnaire réel enregistré "
                            "pour cette action"
                        )
                        status = RuleStatus.BLOCKED
                    else:
                        try:
                            handler_result = handler({
                                "action": action.action,
                                "target": action.target,
                                "parameters": copy.deepcopy(
                                    action.parameters
                                ),
                                "resource": resource,
                                "rule_id": rule.rule_id,
                            })
                            action_result["status"] = "executed"
                            action_result["result"] = (
                                handler_result or {}
                            )
                        except Exception as exc:
                            action_result["status"] = "error"
                            action_result["reason"] = str(exc)
                            status = RuleStatus.ERROR

                actions.append(action_result)

        explanation = {
            "summary": (
                "Toutes les conditions sont validées"
                if matched
                else (
                    "Une ou plusieurs conditions "
                    "sont refusées"
                )
            ),
            "passed_conditions": sum(
                1
                for item in condition_results
                if item["passed"]
            ),
            "failed_conditions": sum(
                1
                for item in condition_results
                if not item["passed"]
            ),
            "total_conditions": len(condition_results),
        }

        decision = {
            "rule_id": rule.rule_id,
            "rule_name": rule.name,
            "priority": rule.priority,
            "status": status.value,
            "matched": matched,
            "conditions": condition_results,
            "actions": actions,
            "explanation": explanation,
        }

        self.repository.record_decision(
            mode=mode.value,
            rule=rule,
            status=status.value,
            matched=matched,
            explanation=decision,
            actions=actions,
            context=context,
        )

        return decision

    def evaluate_all(
        self,
        *,
        context: dict[str, Any] | None = None,
        mode: ExecutionMode = ExecutionMode.SIMULATION,
    ) -> dict[str, Any]:
        self.initialize()
        evaluated_context = copy.deepcopy(context or {})
        rules = self.repository.list(enabled_only=False)
        decisions: list[dict[str, Any]] = []
        reserved_resources: set[str] = set()

        try:
            for rule in rules:
                decision = self.evaluate_rule(
                    rule,
                    evaluated_context,
                    mode=mode,
                    blocked_resources=reserved_resources,
                )
                decisions.append(decision)

                if (
                    decision["matched"]
                    and decision["status"]
                    == RuleStatus.MATCHED.value
                ):
                    reserved_resources.update(
                        action.resource or action.target
                        for action in rule.actions
                    )

                    if rule.stop_on_match:
                        break

            self.evaluation_count += 1
            self.last_evaluation_at = (
                datetime.now(timezone.utc).isoformat()
            )
            self.last_error = None
        except Exception as exc:
            self.last_error = str(exc)
            logger.exception(
                "Échec du moteur de règles"
            )
            raise

        return {
            "mode": mode.value,
            "evaluated_at": self.last_evaluation_at,
            "rule_count": len(rules),
            "matched_count": sum(
                1
                for item in decisions
                if item["matched"]
            ),
            "decisions": decisions,
            "reserved_resources": sorted(
                reserved_resources
            ),
        }

    def diagnostics(self) -> dict[str, Any]:
        self.initialize()
        rules = self.repository.list()

        return {
            "rule_count": len(rules),
            "enabled_count": sum(
                1
                for rule in rules
                if rule.enabled
            ),
            "evaluation_count": self.evaluation_count,
            "last_evaluation_at":
                self.last_evaluation_at,
            "last_error": self.last_error,
            "registered_real_actions": sorted(
                self._action_handlers
            ),
            "real_mode_safe": True,
        }
