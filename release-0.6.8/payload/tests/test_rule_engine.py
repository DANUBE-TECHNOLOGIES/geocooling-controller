from __future__ import annotations

import unittest

from app.rules.models import AutomationRule, ConditionOperator, ExecutionMode, RuleAction, RuleCondition
from app.rules.repository import MemoryRuleRepository
from app.rules.service import RuleEngineService


class RuleEngineTests(unittest.TestCase):
    def setUp(self) -> None:
        self.repository = MemoryRuleRepository()
        self.service = RuleEngineService(repository=self.repository)

    def test_priority_arbitration(self) -> None:
        for name, priority in (("Sécurité", 100), ("Confort", 60)):
            self.repository.save(AutomationRule(
                name=name,
                priority=priority,
                conditions=[],
                actions=[RuleAction("stop", "geocooling", resource="geocooling")],
            ))
        result = self.service.evaluate_all(context={}, mode=ExecutionMode.SIMULATION)
        self.assertEqual(result["decisions"][0]["status"], "matched")
        self.assertEqual(result["decisions"][1]["status"], "blocked")

    def test_condition_evaluation(self) -> None:
        self.repository.save(AutomationRule(
            name="Température haute",
            priority=60,
            conditions=[RuleCondition("thermal.indoor_temperature", ConditionOperator.GT, 24)],
            actions=[RuleAction("start", "geocooling")],
        ))
        result = self.service.evaluate_all(
            context={"thermal": {"indoor_temperature": 25.5}},
            mode=ExecutionMode.SIMULATION,
        )
        self.assertEqual(result["matched_count"], 1)


if __name__ == "__main__":
    unittest.main()
