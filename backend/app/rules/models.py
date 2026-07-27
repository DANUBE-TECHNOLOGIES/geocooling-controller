from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from enum import StrEnum
from typing import Any
from uuid import uuid4


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class ConditionOperator(StrEnum):
    EQ = "eq"
    NE = "ne"
    GT = "gt"
    GTE = "gte"
    LT = "lt"
    LTE = "lte"
    IN = "in"
    NOT_IN = "not_in"
    EXISTS = "exists"
    TRUTHY = "truthy"
    FALSY = "falsy"


class RuleStatus(StrEnum):
    MATCHED = "matched"
    NOT_MATCHED = "not_matched"
    DISABLED = "disabled"
    BLOCKED = "blocked"
    ERROR = "error"


class ExecutionMode(StrEnum):
    SIMULATION = "simulation"
    REAL = "real"


@dataclass(slots=True)
class RuleCondition:
    path: str
    operator: ConditionOperator
    expected: Any = None
    label: str | None = None


@dataclass(slots=True)
class RuleAction:
    action: str
    target: str
    parameters: dict[str, Any] = field(default_factory=dict)
    resource: str | None = None


@dataclass(slots=True)
class AutomationRule:
    name: str
    priority: int
    conditions: list[RuleCondition]
    actions: list[RuleAction]
    enabled: bool = True
    description: str | None = None
    stop_on_match: bool = False
    rule_id: str = field(default_factory=lambda: str(uuid4()))
    created_at: datetime = field(default_factory=utc_now)
    updated_at: datetime = field(default_factory=utc_now)

    def to_dict(self) -> dict[str, Any]:
        payload = asdict(self)
        payload["conditions"] = [
            {**asdict(item), "operator": item.operator.value}
            for item in self.conditions
        ]
        payload["created_at"] = self.created_at.isoformat()
        payload["updated_at"] = self.updated_at.isoformat()
        return payload
