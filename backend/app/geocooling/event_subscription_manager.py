"""
C013.0R2 — Event Subscription Manager.

Gestion centralisée, thread-safe et non intrusive des
abonnements aux événements GeoCooling.
"""

from __future__ import annotations

import inspect
import threading
import time
import uuid

from collections import defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any, Callable


EventCallback = Callable[..., Any]


@dataclass(frozen=True)
class EventSubscription:
    subscription_id: str
    event_type: str
    callback: EventCallback
    callback_name: str
    created_at: str
    once: bool = False


class EventSubscriptionManager:
    """
    Gestionnaire d'abonnements aux événements.

    Un abonnement peut viser :
      - un type précis, par exemple ``brain.decision`` ;
      - le wildcard ``*`` pour recevoir tous les événements.

    Une erreur dans un callback est toujours neutralisée.
    """

    COMPONENT_NAME = "event_subscription_manager"
    PATCH_VERSION = "C013.0R2"

    def __init__(
        self,
        *,
        history_capacity: int = 200,
    ) -> None:
        capacity = int(history_capacity)

        if capacity <= 0:
            raise ValueError(
                "history_capacity doit être positif."
            )

        self._lock = threading.RLock()

        self._subscriptions: dict[
            str,
            EventSubscription,
        ] = {}

        self._subscriptions_by_type: dict[
            str,
            set[str],
        ] = defaultdict(set)

        self._history = deque(
            maxlen=capacity,
        )

        self._created_at = self._utc_now()

        self._metrics = {
            "subscription_count": 0,
            "dispatch_count": 0,
            "delivery_count": 0,
            "callback_success_count": 0,
            "callback_error_count": 0,
            "unsubscribe_count": 0,
            "last_dispatch_at": None,
            "last_delivery_at": None,
            "last_error_at": None,
            "last_error": None,
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @staticmethod
    def _normalize_event_type(
        event_type: Any,
    ) -> str:
        value = str(event_type).strip()

        if not value:
            raise ValueError(
                "event_type ne peut pas être vide."
            )

        return value

    @staticmethod
    def _callback_name(
        callback: EventCallback,
    ) -> str:
        module = getattr(
            callback,
            "__module__",
            None,
        )

        name = getattr(
            callback,
            "__qualname__",
            None,
        )

        if name is None:
            name = getattr(
                callback,
                "__name__",
                type(callback).__name__,
            )

        if module:
            return f"{module}.{name}"

        return str(name)

    @staticmethod
    def _event_type_from_event(
        event: Any,
    ) -> str | None:
        if isinstance(event, dict):
            for key in (
                "event_type",
                "type",
                "name",
            ):
                value = event.get(key)

                if value is not None:
                    return str(value)

        for attribute in (
            "event_type",
            "type",
            "name",
        ):
            try:
                value = getattr(
                    event,
                    attribute,
                )
            except Exception:
                continue

            if value is not None:
                return str(value)

        return None

    def subscribe(
        self,
        event_type: str,
        callback: EventCallback,
        *,
        once: bool = False,
        subscription_id: str | None = None,
    ) -> str:
        normalized_type = self._normalize_event_type(
            event_type
        )

        if not callable(callback):
            raise TypeError(
                "callback doit être appelable."
            )

        identifier = (
            str(subscription_id).strip()
            if subscription_id is not None
            else uuid.uuid4().hex
        )

        if not identifier:
            raise ValueError(
                "subscription_id ne peut pas être vide."
            )

        subscription = EventSubscription(
            subscription_id=identifier,
            event_type=normalized_type,
            callback=callback,
            callback_name=self._callback_name(
                callback
            ),
            created_at=self._utc_now(),
            once=bool(once),
        )

        with self._lock:
            if identifier in self._subscriptions:
                raise ValueError(
                    "subscription_id déjà utilisé : "
                    f"{identifier}"
                )

            self._subscriptions[
                identifier
            ] = subscription

            self._subscriptions_by_type[
                normalized_type
            ].add(identifier)

            self._metrics[
                "subscription_count"
            ] = len(self._subscriptions)

        return identifier

    def unsubscribe(
        self,
        subscription_id: str,
    ) -> bool:
        identifier = str(
            subscription_id
        ).strip()

        if not identifier:
            return False

        with self._lock:
            subscription = self._subscriptions.pop(
                identifier,
                None,
            )

            if subscription is None:
                return False

            identifiers = self._subscriptions_by_type.get(
                subscription.event_type
            )

            if identifiers is not None:
                identifiers.discard(identifier)

                if not identifiers:
                    self._subscriptions_by_type.pop(
                        subscription.event_type,
                        None,
                    )

            self._metrics[
                "subscription_count"
            ] = len(self._subscriptions)

            self._metrics[
                "unsubscribe_count"
            ] += 1

        return True

    def unsubscribe_callback(
        self,
        callback: EventCallback,
        *,
        event_type: str | None = None,
    ) -> int:
        normalized_type = (
            self._normalize_event_type(event_type)
            if event_type is not None
            else None
        )

        with self._lock:
            identifiers = [
                identifier
                for identifier, subscription
                in self._subscriptions.items()
                if (
                    subscription.callback is callback
                    and (
                        normalized_type is None
                        or subscription.event_type
                        == normalized_type
                    )
                )
            ]

        removed = 0

        for identifier in identifiers:
            if self.unsubscribe(identifier):
                removed += 1

        return removed

    def clear(
        self,
        event_type: str | None = None,
    ) -> int:
        normalized_type = (
            self._normalize_event_type(event_type)
            if event_type is not None
            else None
        )

        with self._lock:
            identifiers = [
                identifier
                for identifier, subscription
                in self._subscriptions.items()
                if (
                    normalized_type is None
                    or subscription.event_type
                    == normalized_type
                )
            ]

        removed = 0

        for identifier in identifiers:
            if self.unsubscribe(identifier):
                removed += 1

        return removed

    @staticmethod
    def _invoke_callback(
        callback: EventCallback,
        *,
        event_type: str,
        event: Any,
    ) -> Any:
        """
        Adapte l'appel à la signature réelle du callback.
        """

        try:
            signature = inspect.signature(
                callback
            )
        except (
            TypeError,
            ValueError,
        ):
            return callback(event)

        parameters = list(
            signature.parameters.values()
        )

        if not parameters:
            return callback()

        names = {
            parameter.name
            for parameter in parameters
        }

        accepts_kwargs = any(
            parameter.kind
            is inspect.Parameter.VAR_KEYWORD
            for parameter in parameters
        )

        accepts_varargs = any(
            parameter.kind
            is inspect.Parameter.VAR_POSITIONAL
            for parameter in parameters
        )

        positional = [
            parameter
            for parameter in parameters
            if parameter.kind
            in (
                inspect.Parameter.POSITIONAL_ONLY,
                inspect.Parameter.POSITIONAL_OR_KEYWORD,
            )
        ]

        required_positional = [
            parameter
            for parameter in positional
            if parameter.default
            is inspect.Parameter.empty
        ]

        if (
            "event_type" in names
            and "event" in names
        ):
            return callback(
                event_type=event_type,
                event=event,
            )

        if accepts_kwargs:
            return callback(
                event_type=event_type,
                event=event,
            )

        if accepts_varargs:
            return callback(
                event_type,
                event,
            )

        if len(required_positional) >= 2:
            return callback(
                event_type,
                event,
            )

        if positional:
            first_name = positional[0].name

            if first_name in (
                "event_type",
                "type",
                "name",
            ):
                return callback(event_type)

            return callback(event)

        return callback()

    def dispatch(
        self,
        event: Any,
        *,
        event_type: str | None = None,
    ) -> dict[str, Any]:
        resolved_type = event_type

        if resolved_type is None:
            resolved_type = self._event_type_from_event(
                event
            )

        if resolved_type is None:
            resolved_type = "unknown"

        normalized_type = self._normalize_event_type(
            resolved_type
        )

        started = time.perf_counter()
        dispatched_at = self._utc_now()

        with self._lock:
            identifiers = list(
                dict.fromkeys(
                    [
                        *sorted(
                            self._subscriptions_by_type.get(
                                normalized_type,
                                set(),
                            )
                        ),
                        *sorted(
                            self._subscriptions_by_type.get(
                                "*",
                                set(),
                            )
                        ),
                    ]
                )
            )

            subscriptions = [
                self._subscriptions[identifier]
                for identifier in identifiers
                if identifier in self._subscriptions
            ]

            self._metrics[
                "dispatch_count"
            ] += 1

            self._metrics[
                "last_dispatch_at"
            ] = dispatched_at

        deliveries: list[dict[str, Any]] = []
        one_shot_identifiers: list[str] = []

        for subscription in subscriptions:
            delivery_started = time.perf_counter()

            try:
                result = self._invoke_callback(
                    subscription.callback,
                    event_type=normalized_type,
                    event=event,
                )

                delivery = {
                    "subscription_id":
                        subscription.subscription_id,
                    "callback":
                        subscription.callback_name,
                    "event_type":
                        normalized_type,
                    "success":
                        True,
                    "result_type":
                        type(result).__name__,
                    "duration_ms":
                        round(
                            (
                                time.perf_counter()
                                - delivery_started
                            )
                            * 1000,
                            3,
                        ),
                    "delivered_at":
                        self._utc_now(),
                }

                with self._lock:
                    self._metrics[
                        "delivery_count"
                    ] += 1

                    self._metrics[
                        "callback_success_count"
                    ] += 1

                    self._metrics[
                        "last_delivery_at"
                    ] = delivery[
                        "delivered_at"
                    ]

            except Exception as exc:
                error_text = (
                    f"{type(exc).__name__}: {exc}"
                )

                delivery = {
                    "subscription_id":
                        subscription.subscription_id,
                    "callback":
                        subscription.callback_name,
                    "event_type":
                        normalized_type,
                    "success":
                        False,
                    "error":
                        error_text,
                    "duration_ms":
                        round(
                            (
                                time.perf_counter()
                                - delivery_started
                            )
                            * 1000,
                            3,
                        ),
                    "delivered_at":
                        self._utc_now(),
                }

                with self._lock:
                    self._metrics[
                        "delivery_count"
                    ] += 1

                    self._metrics[
                        "callback_error_count"
                    ] += 1

                    self._metrics[
                        "last_error_at"
                    ] = delivery[
                        "delivered_at"
                    ]

                    self._metrics[
                        "last_error"
                    ] = error_text

            deliveries.append(delivery)

            if subscription.once:
                one_shot_identifiers.append(
                    subscription.subscription_id
                )

        for identifier in one_shot_identifiers:
            self.unsubscribe(identifier)

        report = {
            "event_type":
                normalized_type,
            "subscriber_count":
                len(subscriptions),
            "delivery_count":
                len(deliveries),
            "success_count":
                sum(
                    1
                    for delivery in deliveries
                    if delivery["success"]
                ),
            "error_count":
                sum(
                    1
                    for delivery in deliveries
                    if not delivery["success"]
                ),
            "duration_ms":
                round(
                    (
                        time.perf_counter()
                        - started
                    )
                    * 1000,
                    3,
                ),
            "dispatched_at":
                dispatched_at,
            "deliveries":
                deliveries,
        }

        with self._lock:
            self._history.append(report)

        return report

    def subscriptions(
        self,
    ) -> list[dict[str, Any]]:
        with self._lock:
            values = list(
                self._subscriptions.values()
            )

        return [
            {
                "subscription_id":
                    subscription.subscription_id,
                "event_type":
                    subscription.event_type,
                "callback":
                    subscription.callback_name,
                "created_at":
                    subscription.created_at,
                "once":
                    subscription.once,
            }
            for subscription in values
        ]

    def history(
        self,
        *,
        limit: int = 20,
    ) -> list[dict[str, Any]]:
        normalized_limit = max(
            0,
            int(limit),
        )

        with self._lock:
            values = list(self._history)

        if normalized_limit == 0:
            return []

        return values[-normalized_limit:]

    def status(
        self,
    ) -> dict[str, Any]:
        with self._lock:
            subscriptions = list(
                self._subscriptions.values()
            )

            metrics = dict(
                self._metrics
            )

            history_count = len(
                self._history
            )

            history_capacity = (
                self._history.maxlen
            )

        by_type: dict[str, int] = {}

        for subscription in subscriptions:
            by_type[
                subscription.event_type
            ] = (
                by_type.get(
                    subscription.event_type,
                    0,
                )
                + 1
            )

        return {
            "overall":
                "OK",
            "component":
                self.COMPONENT_NAME,
            "patch_version":
                self.PATCH_VERSION,
            "running":
                True,
            "created_at":
                self._created_at,
            "subscription_count":
                len(subscriptions),
            "subscriptions_by_type":
                dict(
                    sorted(
                        by_type.items()
                    )
                ),
            "subscriptions":
                self.subscriptions(),
            "history_count":
                history_count,
            "history_capacity":
                history_capacity,
            "metrics":
                metrics,
        }
