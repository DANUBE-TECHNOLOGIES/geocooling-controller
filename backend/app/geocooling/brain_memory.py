from __future__ import annotations

import json
from datetime import datetime, timezone
from typing import Any
from uuid import UUID

from sqlalchemy import Engine, text

from app.geocooling.models import ManualCommand


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def _json_value(value: dict[str, Any] | None) -> str:
    return json.dumps(
        value or {},
        ensure_ascii=False,
        default=str,
    )


class BrainMemory:
    """
    Historien PostgreSQL du module GeoCooling.

    Cette classe centralise la persistance :
    - des décisions du Brain ;
    - des commandes manuelles ;
    - des événements techniques et de sécurité.

    Elle ne pilote aucun équipement.
    """

    def __init__(self, engine: Engine) -> None:
        self.engine = engine

    def initialize(self) -> None:
        """
        Crée les tables et index nécessaires.

        L'opération est idempotente et peut être exécutée à chaque
        démarrage du contrôleur.
        """

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS brain_decisions (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        mode TEXT NOT NULL,
                        decision TEXT NOT NULL,
                        confidence DOUBLE PRECISION,
                        reason TEXT,
                        state TEXT,
                        requested_action TEXT,
                        executed_action TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_brain_decisions_created_at
                    ON brain_decisions (created_at DESC)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_brain_decisions_decision
                    ON brain_decisions (decision)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS manual_commands (
                        id UUID PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL,
                        expires_at TIMESTAMPTZ NOT NULL,
                        finished_at TIMESTAMPTZ,
                        requested_by TEXT NOT NULL,
                        command TEXT NOT NULL,
                        status TEXT NOT NULL,
                        duration_seconds INTEGER NOT NULL,
                        reason TEXT,
                        refusal_reason TEXT,
                        metadata JSONB NOT NULL DEFAULT '{}'::jsonb,
                        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        CONSTRAINT manual_commands_duration_positive
                            CHECK (duration_seconds > 0)
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_manual_commands_created_at
                    ON manual_commands (created_at DESC)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_manual_commands_status
                    ON manual_commands (status)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS brain_events (
                        id BIGSERIAL PRIMARY KEY,
                        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
                        level TEXT NOT NULL,
                        event_type TEXT NOT NULL,
                        reason TEXT,
                        source TEXT NOT NULL DEFAULT 'geocooling',
                        details JSONB NOT NULL DEFAULT '{}'::jsonb
                    )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_brain_events_created_at
                    ON brain_events (created_at DESC)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_brain_events_event_type
                    ON brain_events (event_type)
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE TABLE IF NOT EXISTS
                        geocooling_adaptive_model (
                            model_key TEXT PRIMARY KEY,
                            schema_version INTEGER NOT NULL,
                            state JSONB NOT NULL
                                DEFAULT '{}'::jsonb,
                            created_at TIMESTAMPTZ NOT NULL
                                DEFAULT NOW(),
                            updated_at TIMESTAMPTZ NOT NULL
                                DEFAULT NOW()
                        )
                    """
                )
            )

            connection.execute(
                text(
                    """
                    CREATE INDEX IF NOT EXISTS
                        idx_geocooling_adaptive_model_updated_at
                    ON geocooling_adaptive_model (
                        updated_at DESC
                    )
                    """
                )
            )

    def save_adaptive_model_state(
        self,
        state: dict[str, Any],
        *,
        model_key: str = "building-default",
    ) -> None:
        """
        Sauvegarde l'état courant du modèle thermique adaptatif.

        Une seule ligne est conservée par bâtiment/model_key.
        """

        if not isinstance(state, dict):
            raise TypeError(
                "L'état du modèle adaptatif doit être un dictionnaire."
            )

        schema_version = int(
            state.get(
                "schema_version",
                1,
            )
        )

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO geocooling_adaptive_model (
                        model_key,
                        schema_version,
                        state,
                        created_at,
                        updated_at
                    )
                    VALUES (
                        :model_key,
                        :schema_version,
                        CAST(:state AS JSONB),
                        NOW(),
                        NOW()
                    )
                    ON CONFLICT (model_key)
                    DO UPDATE SET
                        schema_version =
                            EXCLUDED.schema_version,
                        state = EXCLUDED.state,
                        updated_at = NOW()
                    """
                ),
                {
                    "model_key": str(model_key),
                    "schema_version":
                        schema_version,
                    "state": _json_value(state),
                },
            )

    def load_adaptive_model_state(
        self,
        *,
        model_key: str = "building-default",
    ) -> dict[str, Any] | None:
        """
        Charge le dernier état persistant du modèle adaptatif.
        """

        with self.engine.connect() as connection:
            row = connection.execute(
                text(
                    """
                    SELECT
                        schema_version,
                        state,
                        created_at,
                        updated_at
                    FROM geocooling_adaptive_model
                    WHERE model_key = :model_key
                    LIMIT 1
                    """
                ),
                {
                    "model_key": str(model_key),
                },
            ).mappings().first()

        if row is None:
            return None

        raw_state = row.get("state")

        if isinstance(raw_state, str):
            try:
                state = json.loads(raw_state)
            except json.JSONDecodeError:
                return None
        elif isinstance(raw_state, dict):
            state = dict(raw_state)
        else:
            return None

        state.setdefault(
            "schema_version",
            int(
                row.get(
                    "schema_version",
                    1,
                )
            ),
        )

        state["_persistence"] = {
            "model_key": str(model_key),
            "created_at": (
                row["created_at"].isoformat()
                if row.get("created_at")
                else None
            ),
            "updated_at": (
                row["updated_at"].isoformat()
                if row.get("updated_at")
                else None
            ),
        }

        return state

    def record_decision(
        self,
        *,
        mode: str,
        decision: str,
        confidence: float | None = None,
        reason: str | None = None,
        state: str | None = None,
        requested_action: str | None = None,
        executed_action: str | None = None,
        metadata: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        """
        Enregistre une décision du Brain et retourne son identifiant.
        """

        timestamp = created_at or utc_now()

        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO brain_decisions (
                        created_at,
                        mode,
                        decision,
                        confidence,
                        reason,
                        state,
                        requested_action,
                        executed_action,
                        metadata
                    )
                    VALUES (
                        :created_at,
                        :mode,
                        :decision,
                        :confidence,
                        :reason,
                        :state,
                        :requested_action,
                        :executed_action,
                        CAST(:metadata AS JSONB)
                    )
                    RETURNING id
                    """
                ),
                {
                    "created_at": timestamp,
                    "mode": str(mode),
                    "decision": str(decision),
                    "confidence": confidence,
                    "reason": reason,
                    "state": state,
                    "requested_action": requested_action,
                    "executed_action": executed_action,
                    "metadata": _json_value(metadata),
                },
            )

            return int(result.scalar_one())

    def save_manual_command(
        self,
        command: ManualCommand,
    ) -> str:
        """
        Insère ou met à jour une commande manuelle.
        """

        payload = command.to_dict()

        with self.engine.begin() as connection:
            connection.execute(
                text(
                    """
                    INSERT INTO manual_commands (
                        id,
                        created_at,
                        expires_at,
                        finished_at,
                        requested_by,
                        command,
                        status,
                        duration_seconds,
                        reason,
                        refusal_reason,
                        metadata,
                        updated_at
                    )
                    VALUES (
                        CAST(:id AS UUID),
                        :created_at,
                        :expires_at,
                        :finished_at,
                        :requested_by,
                        :command,
                        :status,
                        :duration_seconds,
                        :reason,
                        :refusal_reason,
                        CAST(:metadata AS JSONB),
                        NOW()
                    )
                    ON CONFLICT (id)
                    DO UPDATE SET
                        expires_at = EXCLUDED.expires_at,
                        finished_at = EXCLUDED.finished_at,
                        requested_by = EXCLUDED.requested_by,
                        command = EXCLUDED.command,
                        status = EXCLUDED.status,
                        duration_seconds = EXCLUDED.duration_seconds,
                        reason = EXCLUDED.reason,
                        refusal_reason = EXCLUDED.refusal_reason,
                        metadata = EXCLUDED.metadata,
                        updated_at = NOW()
                    """
                ),
                {
                    "id": str(command.id),
                    "created_at": command.created_at,
                    "expires_at": command.expires_at,
                    "finished_at": command.finished_at,
                    "requested_by": command.requested_by,
                    "command": command.command.value,
                    "status": command.status.value,
                    "duration_seconds": command.duration_seconds,
                    "reason": command.reason,
                    "refusal_reason": command.refusal_reason,
                    "metadata": _json_value(payload.get("metadata")),
                },
            )

        return str(command.id)

    def record_event(
        self,
        *,
        level: str,
        event_type: str,
        reason: str | None = None,
        source: str = "geocooling",
        details: dict[str, Any] | None = None,
        created_at: datetime | None = None,
    ) -> int:
        """
        Enregistre un événement technique, fonctionnel ou de sécurité.
        """

        timestamp = created_at or utc_now()

        with self.engine.begin() as connection:
            result = connection.execute(
                text(
                    """
                    INSERT INTO brain_events (
                        created_at,
                        level,
                        event_type,
                        reason,
                        source,
                        details
                    )
                    VALUES (
                        :created_at,
                        :level,
                        :event_type,
                        :reason,
                        :source,
                        CAST(:details AS JSONB)
                    )
                    RETURNING id
                    """
                ),
                {
                    "created_at": timestamp,
                    "level": str(level).upper(),
                    "event_type": str(event_type),
                    "reason": reason,
                    "source": str(source),
                    "details": _json_value(details),
                },
            )

            return int(result.scalar_one())

    def recent_decisions(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_limit = self._validate_limit(limit)

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        created_at,
                        mode,
                        decision,
                        confidence,
                        reason,
                        state,
                        requested_action,
                        executed_action,
                        metadata
                    FROM brain_decisions
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": normalized_limit},
            ).mappings()

            return [
                self._serialize_row(row)
                for row in rows
            ]

    def recent_manual_commands(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_limit = self._validate_limit(limit)

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        created_at,
                        expires_at,
                        finished_at,
                        requested_by,
                        command,
                        status,
                        duration_seconds,
                        reason,
                        refusal_reason,
                        metadata,
                        updated_at
                    FROM manual_commands
                    ORDER BY created_at DESC
                    LIMIT :limit
                    """
                ),
                {"limit": normalized_limit},
            ).mappings()

            return [
                self._serialize_row(row)
                for row in rows
            ]

    def recent_events(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        normalized_limit = self._validate_limit(limit)

        with self.engine.connect() as connection:
            rows = connection.execute(
                text(
                    """
                    SELECT
                        id,
                        created_at,
                        level,
                        event_type,
                        reason,
                        source,
                        details
                    FROM brain_events
                    ORDER BY created_at DESC, id DESC
                    LIMIT :limit
                    """
                ),
                {"limit": normalized_limit},
            ).mappings()

            return [
                self._serialize_row(row)
                for row in rows
            ]

    def table_counts(self) -> dict[str, int]:
        """
        Retourne le nombre de lignes de chaque table BrainMemory.
        """

        counts: dict[str, int] = {}

        with self.engine.connect() as connection:
            for table_name in (
                "brain_decisions",
                "manual_commands",
                "brain_events",
            ):
                value = connection.execute(
                    text(
                        f"SELECT COUNT(*) FROM {table_name}"
                    )
                ).scalar_one()

                counts[table_name] = int(value)

        return counts

    @staticmethod
    def _validate_limit(limit: int) -> int:
        if isinstance(limit, bool):
            raise TypeError("limit doit être un entier")

        try:
            normalized = int(limit)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "limit doit être un entier"
            ) from exc

        if normalized < 1:
            raise ValueError(
                "limit doit être supérieur ou égal à 1"
            )

        return min(normalized, 500)

    @staticmethod
    def _serialize_row(
        row: Any,
    ) -> dict[str, Any]:
        result: dict[str, Any] = {}

        for key, value in dict(row).items():
            if isinstance(value, datetime):
                result[key] = value.isoformat()
            elif isinstance(value, UUID):
                result[key] = str(value)
            else:
                result[key] = value

        return result
