from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import Engine, text

from app.rules.models import (
    AutomationRule,
    ConditionOperator,
    RuleAction,
    RuleCondition,
)


class RuleRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine
        self._initialized = False

    def initialize(self) -> None:
        if self._initialized:
            return

        with self.engine.begin() as connection:
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS automation_rules (
                    rule_id UUID PRIMARY KEY,
                    name VARCHAR(180) NOT NULL,
                    description TEXT,
                    priority INTEGER NOT NULL CHECK (priority BETWEEN 0 AND 1000),
                    enabled BOOLEAN NOT NULL DEFAULT TRUE,
                    stop_on_match BOOLEAN NOT NULL DEFAULT FALSE,
                    conditions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
                )
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_automation_rules_enabled_priority
                ON automation_rules (enabled, priority DESC)
            """))
            connection.execute(text("""
                CREATE TABLE IF NOT EXISTS rule_decisions (
                    decision_id BIGSERIAL PRIMARY KEY,
                    evaluated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                    mode VARCHAR(20) NOT NULL,
                    rule_id UUID,
                    rule_name VARCHAR(180) NOT NULL,
                    priority INTEGER NOT NULL,
                    status VARCHAR(30) NOT NULL,
                    matched BOOLEAN NOT NULL,
                    explanation JSONB NOT NULL DEFAULT '{}'::jsonb,
                    actions JSONB NOT NULL DEFAULT '[]'::jsonb,
                    context_snapshot JSONB NOT NULL DEFAULT '{}'::jsonb
                )
            """))
            connection.execute(text("""
                CREATE INDEX IF NOT EXISTS idx_rule_decisions_time
                ON rule_decisions (evaluated_at DESC)
            """))

        self._initialized = True

    @staticmethod
    def _row_to_rule(row: Any) -> AutomationRule:
        return AutomationRule(
            rule_id=str(row["rule_id"]),
            name=row["name"],
            description=row["description"],
            priority=row["priority"],
            enabled=row["enabled"],
            stop_on_match=row["stop_on_match"],
            conditions=[
                RuleCondition(
                    path=item["path"],
                    operator=ConditionOperator(item["operator"]),
                    expected=item.get("expected"),
                    label=item.get("label"),
                )
                for item in (row["conditions"] or [])
            ],
            actions=[
                RuleAction(
                    action=item["action"],
                    target=item["target"],
                    parameters=dict(item.get("parameters") or {}),
                    resource=item.get("resource"),
                )
                for item in (row["actions"] or [])
            ],
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )

    def list(self, enabled_only: bool = False) -> list[AutomationRule]:
        self.initialize()
        where_clause = "WHERE enabled = TRUE" if enabled_only else ""

        with self.engine.connect() as connection:
            rows = connection.execute(text(f"""
                SELECT *
                FROM automation_rules
                {where_clause}
                ORDER BY priority DESC, name ASC
            """)).mappings().all()

        return [self._row_to_rule(row) for row in rows]

    def get(self, rule_id: str) -> AutomationRule | None:
        self.initialize()

        with self.engine.connect() as connection:
            row = connection.execute(
                text("""
                    SELECT *
                    FROM automation_rules
                    WHERE rule_id = CAST(:rule_id AS UUID)
                """),
                {"rule_id": rule_id},
            ).mappings().first()

        return self._row_to_rule(row) if row else None

    def save(self, rule: AutomationRule) -> AutomationRule:
        self.initialize()
        rule.updated_at = datetime.now(timezone.utc)
        payload = rule.to_dict()

        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO automation_rules (
                    rule_id,
                    name,
                    description,
                    priority,
                    enabled,
                    stop_on_match,
                    conditions,
                    actions,
                    created_at,
                    updated_at
                )
                VALUES (
                    CAST(:rule_id AS UUID),
                    :name,
                    :description,
                    :priority,
                    :enabled,
                    :stop_on_match,
                    CAST(:conditions AS JSONB),
                    CAST(:actions AS JSONB),
                    :created_at,
                    :updated_at
                )
                ON CONFLICT (rule_id)
                DO UPDATE SET
                    name = EXCLUDED.name,
                    description = EXCLUDED.description,
                    priority = EXCLUDED.priority,
                    enabled = EXCLUDED.enabled,
                    stop_on_match = EXCLUDED.stop_on_match,
                    conditions = EXCLUDED.conditions,
                    actions = EXCLUDED.actions,
                    updated_at = EXCLUDED.updated_at
            """), {
                **payload,
                "conditions": json.dumps(payload["conditions"], default=str),
                "actions": json.dumps(payload["actions"], default=str),
            })

        return rule

    def delete(self, rule_id: str) -> bool:
        self.initialize()

        with self.engine.begin() as connection:
            result = connection.execute(
                text("""
                    DELETE FROM automation_rules
                    WHERE rule_id = CAST(:rule_id AS UUID)
                """),
                {"rule_id": rule_id},
            )

        return bool(result.rowcount)

    def record_decision(
        self,
        *,
        mode: str,
        rule: AutomationRule,
        status: str,
        matched: bool,
        explanation: dict[str, Any],
        actions: list[dict[str, Any]],
        context: dict[str, Any],
    ) -> None:
        self.initialize()

        with self.engine.begin() as connection:
            connection.execute(text("""
                INSERT INTO rule_decisions (
                    mode,
                    rule_id,
                    rule_name,
                    priority,
                    status,
                    matched,
                    explanation,
                    actions,
                    context_snapshot
                )
                VALUES (
                    :mode,
                    CAST(:rule_id AS UUID),
                    :rule_name,
                    :priority,
                    :status,
                    :matched,
                    CAST(:explanation AS JSONB),
                    CAST(:actions AS JSONB),
                    CAST(:context AS JSONB)
                )
            """), {
                "mode": mode,
                "rule_id": rule.rule_id,
                "rule_name": rule.name,
                "priority": rule.priority,
                "status": status,
                "matched": matched,
                "explanation": json.dumps(explanation, default=str),
                "actions": json.dumps(actions, default=str),
                "context": json.dumps(context, default=str),
            })

    def decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        self.initialize()

        with self.engine.connect() as connection:
            rows = connection.execute(text("""
                SELECT
                    decision_id,
                    evaluated_at,
                    mode,
                    rule_id,
                    rule_name,
                    priority,
                    status,
                    matched,
                    explanation,
                    actions
                FROM rule_decisions
                ORDER BY evaluated_at DESC
                LIMIT :limit
            """), {"limit": min(max(limit, 1), 500)}).mappings().all()

        return [
            {
                **dict(row),
                "rule_id": str(row["rule_id"]) if row["rule_id"] else None,
                "evaluated_at": row["evaluated_at"].isoformat(),
                "explanation": dict(row["explanation"] or {}),
                "actions": list(row["actions"] or []),
            }
            for row in rows
        ]


class MemoryRuleRepository:
    def __init__(self) -> None:
        self.rules: dict[str, AutomationRule] = {}
        self.history: list[dict[str, Any]] = []

    def initialize(self) -> None:
        return None

    def list(self, enabled_only: bool = False) -> list[AutomationRule]:
        rules = list(self.rules.values())

        if enabled_only:
            rules = [rule for rule in rules if rule.enabled]

        return sorted(rules, key=lambda rule: (-rule.priority, rule.name))

    def get(self, rule_id: str) -> AutomationRule | None:
        return self.rules.get(rule_id)

    def save(self, rule: AutomationRule) -> AutomationRule:
        self.rules[rule.rule_id] = rule
        return rule

    def delete(self, rule_id: str) -> bool:
        return self.rules.pop(rule_id, None) is not None

    def record_decision(self, **payload: Any) -> None:
        self.history.append(payload)

    def decisions(self, limit: int = 100) -> list[dict[str, Any]]:
        return list(reversed(self.history[-limit:]))
