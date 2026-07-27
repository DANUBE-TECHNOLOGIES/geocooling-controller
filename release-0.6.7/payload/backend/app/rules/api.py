from __future__ import annotations

from typing import Any

from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel, Field

from app.rules.models import (
    AutomationRule,
    ConditionOperator,
    ExecutionMode,
    RuleAction,
    RuleCondition,
)
from app.rules.service import RuleEngineService

router = APIRouter(
    prefix="/rules",
    tags=["Rule Engine"],
)
_service: RuleEngineService | None = None


class ConditionPayload(BaseModel):
    path: str = Field(
        min_length=1,
        max_length=240,
    )
    operator: ConditionOperator
    expected: Any = None
    label: str | None = Field(
        default=None,
        max_length=240,
    )


class ActionPayload(BaseModel):
    action: str = Field(
        min_length=1,
        max_length=120,
    )
    target: str = Field(
        min_length=1,
        max_length=120,
    )
    parameters: dict[str, Any] = Field(
        default_factory=dict
    )
    resource: str | None = Field(
        default=None,
        max_length=120,
    )


class RulePayload(BaseModel):
    name: str = Field(
        min_length=3,
        max_length=180,
    )
    description: str | None = None
    priority: int = Field(
        ge=0,
        le=1000,
    )
    enabled: bool = True
    stop_on_match: bool = False
    conditions: list[ConditionPayload] = Field(
        default_factory=list
    )
    actions: list[ActionPayload] = Field(
        min_length=1
    )


class EvaluatePayload(BaseModel):
    mode: ExecutionMode = (
        ExecutionMode.SIMULATION
    )
    context: dict[str, Any] | None = None


def configure_rules_router(
    service: RuleEngineService,
) -> None:
    global _service
    _service = service


def get_service() -> RuleEngineService:
    if _service is None:
        raise HTTPException(
            status_code=503,
            detail="Rule Engine non configuré",
        )

    return _service


def make_rule(
    payload: RulePayload,
    rule_id: str | None = None,
) -> AutomationRule:
    kwargs: dict[str, Any] = {}

    if rule_id:
        kwargs["rule_id"] = rule_id

    return AutomationRule(
        **kwargs,
        name=payload.name,
        description=payload.description,
        priority=payload.priority,
        enabled=payload.enabled,
        stop_on_match=payload.stop_on_match,
        conditions=[
            RuleCondition(
                path=item.path,
                operator=item.operator,
                expected=item.expected,
                label=item.label,
            )
            for item in payload.conditions
        ],
        actions=[
            RuleAction(
                action=item.action,
                target=item.target,
                parameters=item.parameters,
                resource=item.resource,
            )
            for item in payload.actions
        ],
    )


@router.get("")
def list_rules(
    enabled_only: bool = False,
) -> dict[str, Any]:
    service = get_service()
    service.initialize()

    items = [
        rule.to_dict()
        for rule in service.repository.list(
            enabled_only
        )
    ]

    return {
        "rules": items,
        "count": len(items),
    }


@router.post("", status_code=201)
def create_rule(
    payload: RulePayload,
) -> dict[str, Any]:
    rule = get_service().repository.save(
        make_rule(payload)
    )
    return rule.to_dict()


@router.put("/{rule_id}")
def update_rule(
    rule_id: str,
    payload: RulePayload,
) -> dict[str, Any]:
    service = get_service()

    if service.repository.get(rule_id) is None:
        raise HTTPException(
            status_code=404,
            detail="Règle introuvable",
        )

    return service.repository.save(
        make_rule(payload, rule_id)
    ).to_dict()


@router.delete("/{rule_id}")
def delete_rule(
    rule_id: str,
) -> dict[str, bool]:
    if not get_service().repository.delete(rule_id):
        raise HTTPException(
            status_code=404,
            detail="Règle introuvable",
        )

    return {"deleted": True}


@router.post("/evaluate")
def evaluate(
    payload: EvaluatePayload,
) -> dict[str, Any]:
    return get_service().evaluate_all(
        context=payload.context,
        mode=payload.mode,
    )


@router.get("/decisions")
def decisions(
    limit: int = Query(
        default=100,
        ge=1,
        le=500,
    ),
) -> dict[str, Any]:
    items = get_service().repository.decisions(
        limit
    )

    return {
        "decisions": items,
        "count": len(items),
    }


@router.get("/diagnostics")
def diagnostics() -> dict[str, Any]:
    return get_service().diagnostics()
