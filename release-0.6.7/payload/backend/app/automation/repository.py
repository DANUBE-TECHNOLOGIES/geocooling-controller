from __future__ import annotations

import json
from typing import Any

from sqlalchemy import Engine, text

from app.automation.models import AutomationExecution


class AutomationRepository:
    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        statements = [
            """
            CREATE TABLE IF NOT EXISTS automation_executions (
                id BIGSERIAL PRIMARY KEY,
                execution_id UUID NOT NULL UNIQUE,
                subsystem TEXT NOT NULL,
                action TEXT NOT NULL,
                mode TEXT NOT NULL,
                state TEXT NOT NULL,
                requested_by TEXT NOT NULL,
                duration_minutes INTEGER,
                reason TEXT,
                message TEXT,
                error TEXT,
                metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                result JSONB NOT NULL DEFAULT '{}'::jsonb,
                created_at TIMESTAMPTZ NOT NULL,
                updated_at TIMESTAMPTZ NOT NULL,
                started_at TIMESTAMPTZ,
                completed_at TIMESTAMPTZ
            )
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_automation_created_at
            ON automation_executions (created_at DESC)
            """,
            """
            CREATE INDEX IF NOT EXISTS idx_automation_state_created
            ON automation_executions (state, created_at DESC)
            """,
        ]
        with self.engine.begin() as connection:
            for statement in statements:
                connection.execute(text(statement))

    def save(self, item: AutomationExecution) -> None:
        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO automation_executions (
                        execution_id, subsystem, action, mode, state,
                        requested_by, duration_minutes, reason, message,
                        error, metadata, result, created_at, updated_at,
                        started_at, completed_at
                    ) VALUES (
                        CAST(:execution_id AS UUID), :subsystem, :action,
                        :mode, :state, :requested_by, :duration_minutes,
                        :reason, :message, :error,
                        CAST(:metadata AS JSONB), CAST(:result AS JSONB),
                        :created_at, :updated_at, :started_at, :completed_at
                    )
                    ON CONFLICT (execution_id) DO UPDATE SET
                        state = EXCLUDED.state,
                        message = EXCLUDED.message,
                        error = EXCLUDED.error,
                        metadata = EXCLUDED.metadata,
                        result = EXCLUDED.result,
                        updated_at = EXCLUDED.updated_at,
                        started_at = EXCLUDED.started_at,
                        completed_at = EXCLUDED.completed_at
                    """
                ),
                {
                    "execution_id": item.execution_id,
                    "subsystem": item.subsystem,
                    "action": item.action.value,
                    "mode": item.mode.value,
                    "state": item.state.value,
                    "requested_by": item.requested_by,
                    "duration_minutes": item.duration_minutes,
                    "reason": item.reason,
                    "message": item.message,
                    "error": item.error,
                    "metadata": json.dumps(item.metadata, default=str),
                    "result": json.dumps(item.result, default=str),
                    "created_at": item.created_at,
                    "updated_at": item.updated_at,
                    "started_at": item.started_at,
                    "completed_at": item.completed_at,
                },
            )

    def list(self, limit: int = 100, state: str | None = None) -> list[dict[str, Any]]:
        where = "WHERE state = :state" if state else ""
        params: dict[str, Any] = {"limit": min(max(limit, 1), 500)}
        if state:
            params["state"] = state
        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    f"""
                    SELECT execution_id, subsystem, action, mode, state,
                           requested_by, duration_minutes, reason, message,
                           error, metadata, result, created_at, updated_at,
                           started_at, completed_at
                    FROM automation_executions
                    {where}
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                params,
            ).mappings().all()
        return [self._row_to_dict(dict(row)) for row in rows]

    def get(self, execution_id: str) -> dict[str, Any] | None:
        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT execution_id, subsystem, action, mode, state,
                           requested_by, duration_minutes, reason, message,
                           error, metadata, result, created_at, updated_at,
                           started_at, completed_at
                    FROM automation_executions
                    WHERE execution_id = CAST(:execution_id AS UUID)
                    LIMIT 1
                    """
                ),
                {"execution_id": execution_id},
            ).mappings().first()
        return self._row_to_dict(dict(row)) if row else None

    @staticmethod
    def _row_to_dict(row: dict[str, Any]) -> dict[str, Any]:
        row["execution_id"] = str(row["execution_id"])
        for key in ("created_at", "updated_at", "started_at", "completed_at"):
            value = row.get(key)
            row[key] = value.isoformat() if value else None
        return row
