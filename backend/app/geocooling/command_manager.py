from __future__ import annotations

import threading
from collections import deque
from datetime import datetime, timezone
from typing import Any

from app.geocooling.models import (
    ManualCommand,
    ManualCommandStatus,
    ManualCommandType,
)


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


class CommandManager:
    """
    Gestionnaire central des commandes manuelles GeoCooling.

    Cette classe ne pilote aucun relais directement.

    Son rôle est de :
    - créer les demandes manuelles ;
    - empêcher plusieurs commandes actives simultanément ;
    - gérer leur cycle de vie ;
    - détecter leur expiration ;
    - conserver un historique en mémoire.

    Le contrôleur restera responsable de l'exécution physique et
    des validations de sécurité.
    """

    DEFAULT_DURATION_SECONDS = 900
    MIN_DURATION_SECONDS = 1
    MAX_DURATION_SECONDS = 14_400
    DEFAULT_HISTORY_SIZE = 200

    def __init__(
        self,
        *,
        history_size: int = DEFAULT_HISTORY_SIZE,
        minimum_duration_seconds: int = MIN_DURATION_SECONDS,
        maximum_duration_seconds: int = MAX_DURATION_SECONDS,
    ) -> None:
        if history_size < 1:
            raise ValueError(
                "history_size doit être supérieur ou égal à 1"
            )

        if minimum_duration_seconds < 1:
            raise ValueError(
                "minimum_duration_seconds doit être supérieur ou égal à 1"
            )

        if maximum_duration_seconds < minimum_duration_seconds:
            raise ValueError(
                "maximum_duration_seconds doit être supérieur ou égal "
                "à minimum_duration_seconds"
            )

        self.minimum_duration_seconds = minimum_duration_seconds
        self.maximum_duration_seconds = maximum_duration_seconds

        self._lock = threading.RLock()
        self._active_command: ManualCommand | None = None
        self._history: deque[ManualCommand] = deque(
            maxlen=history_size
        )

    def _normalize_requested_by(
        self,
        requested_by: str,
    ) -> str:
        if not isinstance(requested_by, str):
            raise TypeError("requested_by doit être une chaîne")

        value = requested_by.strip()

        if not value:
            return "unknown"

        return value[:120]

    def _normalize_reason(
        self,
        reason: str,
    ) -> str:
        if not isinstance(reason, str):
            raise TypeError("reason doit être une chaîne")

        return reason.strip()[:500]

    def _validate_duration(
        self,
        duration_seconds: int,
    ) -> int:
        if isinstance(duration_seconds, bool):
            raise TypeError(
                "duration_seconds doit être un entier"
            )

        try:
            duration = int(duration_seconds)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "duration_seconds doit être un entier"
            ) from exc

        if duration < self.minimum_duration_seconds:
            raise ValueError(
                "duration_seconds doit être supérieur ou égal à "
                f"{self.minimum_duration_seconds}"
            )

        if duration > self.maximum_duration_seconds:
            raise ValueError(
                "duration_seconds doit être inférieur ou égal à "
                f"{self.maximum_duration_seconds}"
            )

        return duration

    def _normalize_metadata(
        self,
        metadata: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if metadata is None:
            return {}

        if not isinstance(metadata, dict):
            raise TypeError("metadata doit être un dictionnaire")

        return dict(metadata)

    def _archive_locked(
        self,
        command: ManualCommand,
    ) -> None:
        if not any(
            item.id == command.id
            for item in self._history
        ):
            self._history.appendleft(command)

    def _cleanup_expired_locked(
        self,
    ) -> ManualCommand | None:
        """
        Expire uniquement une commande encore en attente.

        Une commande ACCEPTED reste active après son échéance afin que
        le contrôleur puisse exécuter sa séquence d'arrêt sécurisé,
        persister le résultat puis clôturer explicitement la commande.

        Retirer automatiquement une commande ACCEPTED empêcherait son
        moniteur d'exécution de déclencher l'arrêt automatique.
        """

        command = self._active_command

        if command is None:
            return None

        if not command.expired:
            return None

        if command.status != ManualCommandStatus.PENDING:
            return None

        command.expire()
        self._archive_locked(command)
        self._active_command = None

        return command

    def cleanup_expired(
        self,
    ) -> dict[str, Any] | None:
        """
        Termine la commande active si sa durée est dépassée.

        Retourne la commande expirée ou None.
        """

        with self._lock:
            command = self._cleanup_expired_locked()

            return (
                command.to_dict()
                if command is not None
                else None
            )

    def active_command(
        self,
    ) -> dict[str, Any] | None:
        """
        Retourne la commande active après contrôle d'expiration.
        """

        with self._lock:
            self._cleanup_expired_locked()

            if self._active_command is None:
                return None

            return self._active_command.to_dict()

    def active_command_object(
        self,
    ) -> ManualCommand | None:
        """
        Retourne l'objet interne.

        Cette méthode est destinée au contrôleur uniquement.
        Le consommateur ne doit pas modifier l'objet directement.
        """

        with self._lock:
            self._cleanup_expired_locked()
            return self._active_command

    def request(
        self,
        *,
        command_type: ManualCommandType | str,
        requested_by: str,
        duration_seconds: int = DEFAULT_DURATION_SECONDS,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """
        Enregistre une nouvelle demande manuelle.

        La demande est créée au statut PENDING. Elle devra ensuite être
        acceptée ou refusée par le contrôleur après vérification des
        sécurités.
        """

        try:
            normalized_type = ManualCommandType(
                str(command_type).upper()
            )
        except ValueError as exc:
            allowed = ", ".join(
                item.value for item in ManualCommandType
            )
            raise ValueError(
                f"Commande inconnue. Valeurs autorisées : {allowed}"
            ) from exc

        if normalized_type == ManualCommandType.CANCEL:
            return self.cancel(
                requested_by=requested_by,
                reason=reason or "Annulation demandée",
            )

        normalized_requested_by = (
            self._normalize_requested_by(requested_by)
        )
        normalized_duration = self._validate_duration(
            duration_seconds
        )
        normalized_reason = self._normalize_reason(reason)
        normalized_metadata = self._normalize_metadata(
            metadata
        )

        with self._lock:
            self._cleanup_expired_locked()

            if self._active_command is not None:
                return {
                    "accepted": False,
                    "reason": (
                        "Une commande manuelle est déjà active"
                    ),
                    "active_command": (
                        self._active_command.to_dict()
                    ),
                }

            command = ManualCommand(
                command=normalized_type,
                requested_by=normalized_requested_by,
                duration_seconds=normalized_duration,
                reason=normalized_reason,
                metadata=normalized_metadata,
            )

            self._active_command = command

            return {
                "accepted": True,
                "reason": "Commande enregistrée en attente de validation",
                "command": command.to_dict(),
            }

    def request_start(
        self,
        *,
        requested_by: str,
        duration_seconds: int = DEFAULT_DURATION_SECONDS,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            command_type=ManualCommandType.START,
            requested_by=requested_by,
            duration_seconds=duration_seconds,
            reason=reason,
            metadata=metadata,
        )

    def request_stop(
        self,
        *,
        requested_by: str,
        duration_seconds: int = DEFAULT_DURATION_SECONDS,
        reason: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        return self.request(
            command_type=ManualCommandType.STOP,
            requested_by=requested_by,
            duration_seconds=duration_seconds,
            reason=reason,
            metadata=metadata,
        )

    def accept_active(
        self,
        *,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Accepte la commande active après validation du contrôleur.
        """

        with self._lock:
            self._cleanup_expired_locked()
            command = self._active_command

            if command is None:
                return {
                    "accepted": False,
                    "reason": "Aucune commande active",
                }

            if command_id and command.id != command_id:
                return {
                    "accepted": False,
                    "reason": "Identifiant de commande incorrect",
                    "active_command": command.to_dict(),
                }

            if command.status == ManualCommandStatus.ACCEPTED:
                return {
                    "accepted": True,
                    "reason": "Commande déjà acceptée",
                    "command": command.to_dict(),
                }

            if command.status != ManualCommandStatus.PENDING:
                return {
                    "accepted": False,
                    "reason": (
                        "La commande ne peut plus être acceptée"
                    ),
                    "command": command.to_dict(),
                }

            command.accept()

            return {
                "accepted": True,
                "reason": "Commande acceptée",
                "command": command.to_dict(),
            }

    def refuse_active(
        self,
        *,
        refusal_reason: str,
        command_id: str | None = None,
    ) -> dict[str, Any]:
        """
        Refuse et archive la commande active.
        """

        normalized_reason = self._normalize_reason(
            refusal_reason
        )

        if not normalized_reason:
            raise ValueError(
                "Une raison de refus est obligatoire"
            )

        with self._lock:
            self._cleanup_expired_locked()
            command = self._active_command

            if command is None:
                return {
                    "accepted": False,
                    "reason": "Aucune commande active",
                }

            if command_id and command.id != command_id:
                return {
                    "accepted": False,
                    "reason": "Identifiant de commande incorrect",
                    "active_command": command.to_dict(),
                }

            command.refuse(normalized_reason)
            self._archive_locked(command)
            self._active_command = None

            return {
                "accepted": True,
                "reason": "Commande refusée",
                "command": command.to_dict(),
            }

    def finish_active(
        self,
        *,
        command_id: str | None = None,
        reason: str = "",
    ) -> dict[str, Any]:
        """
        Termine et archive la commande active.
        """

        normalized_reason = self._normalize_reason(reason)

        with self._lock:
            self._cleanup_expired_locked()
            command = self._active_command

            if command is None:
                return {
                    "accepted": False,
                    "reason": "Aucune commande active",
                }

            if command_id and command.id != command_id:
                return {
                    "accepted": False,
                    "reason": "Identifiant de commande incorrect",
                    "active_command": command.to_dict(),
                }

            if normalized_reason:
                command.metadata["finish_reason"] = (
                    normalized_reason
                )

            command.finish()
            self._archive_locked(command)
            self._active_command = None

            return {
                "accepted": True,
                "reason": "Commande terminée",
                "command": command.to_dict(),
            }

    def cancel(
        self,
        *,
        requested_by: str,
        reason: str = "Annulation demandée",
    ) -> dict[str, Any]:
        """
        Annule et archive la commande active.
        """

        normalized_requested_by = (
            self._normalize_requested_by(requested_by)
        )
        normalized_reason = self._normalize_reason(reason)

        with self._lock:
            self._cleanup_expired_locked()
            command = self._active_command

            if command is None:
                return {
                    "accepted": False,
                    "reason": "Aucune commande active à annuler",
                }

            command.metadata["cancelled_by"] = (
                normalized_requested_by
            )
            command.metadata["cancel_reason"] = (
                normalized_reason
                or "Annulation demandée"
            )

            command.cancel()
            self._archive_locked(command)
            self._active_command = None

            return {
                "accepted": True,
                "reason": "Commande annulée",
                "command": command.to_dict(),
            }

    def history(
        self,
        limit: int = 50,
    ) -> list[dict[str, Any]]:
        """
        Retourne les dernières commandes terminées.
        """

        if isinstance(limit, bool):
            raise TypeError("limit doit être un entier")

        try:
            normalized_limit = int(limit)
        except (TypeError, ValueError) as exc:
            raise TypeError(
                "limit doit être un entier"
            ) from exc

        if normalized_limit < 1:
            raise ValueError(
                "limit doit être supérieur ou égal à 1"
            )

        with self._lock:
            self._cleanup_expired_locked()

            return [
                command.to_dict()
                for command in list(self._history)[
                    :normalized_limit
                ]
            ]

    def status(
        self,
    ) -> dict[str, Any]:
        """
        Retourne l'état complet du gestionnaire.
        """

        with self._lock:
            expired = self._cleanup_expired_locked()

            return {
                "active": self._active_command is not None,
                "active_command": (
                    self._active_command.to_dict()
                    if self._active_command
                    else None
                ),
                "expired_command": (
                    expired.to_dict()
                    if expired
                    else None
                ),
                "history_count": len(self._history),
                "duration_limits": {
                    "minimum_seconds": (
                        self.minimum_duration_seconds
                    ),
                    "maximum_seconds": (
                        self.maximum_duration_seconds
                    ),
                    "default_seconds": (
                        self.DEFAULT_DURATION_SECONDS
                    ),
                },
            }
