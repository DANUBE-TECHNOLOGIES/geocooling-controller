"""Registre d'exécution centralisé du sous-système GeoCooling.

Le Runtime Manager conserve une référence unique vers les services créés par
l'API GeoCooling. Il constitue le point d'accès commun destiné aux futures
briques :

- State Cache ;
- Dashboard ;
- Export diagnostic ;
- WebSocket ;
- interface de supervision.

Cette première migration reste volontairement non invasive : elle réutilise
les instances existantes et ne recrée aucun Controller ou thread.
"""

from __future__ import annotations

import threading
from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


class GeoCoolingRuntime:
    """Registre central des composants GeoCooling."""

    _singleton: "GeoCoolingRuntime | None" = None
    _singleton_lock = threading.RLock()

    EXPECTED_COMPONENTS = (
        "controller",
        "health_manager",
        "commissioning_manager",
        "commissioning_test_manager",
        "flight_recorder",
        "event_timeline",
        "watchdog",
    )

    def __new__(
        cls,
        *args: Any,
        **kwargs: Any,
    ) -> "GeoCoolingRuntime":
        with cls._singleton_lock:
            if cls._singleton is None:
                cls._singleton = super().__new__(cls)

            return cls._singleton

    def __init__(
        self,
        *,
        controller: Any | None = None,
        health_manager: Any | None = None,
        commissioning_manager: Any | None = None,
        commissioning_test_manager: Any | None = None,
        flight_recorder: Any | None = None,
        event_timeline: Any | None = None,
        watchdog: Any | None = None,
    ) -> None:
        if getattr(self, "_initialized", False):
            self.register_many(
                controller=controller,
                health_manager=health_manager,
                commissioning_manager=commissioning_manager,
                commissioning_test_manager=commissioning_test_manager,
                flight_recorder=flight_recorder,
                event_timeline=event_timeline,
                watchdog=watchdog,
            )
            return

        self._lock = threading.RLock()
        self._created_at = utc_now_iso()
        self._updated_at = self._created_at
        self._components: dict[str, Any] = {}
        self._registrations: dict[str, int] = {}
        self._conflicts: list[dict[str, Any]] = []
        self._initialized = True

        self.register_many(
            controller=controller,
            health_manager=health_manager,
            commissioning_manager=commissioning_manager,
            commissioning_test_manager=commissioning_test_manager,
            flight_recorder=flight_recorder,
            event_timeline=event_timeline,
            watchdog=watchdog,
        )

    @classmethod
    def instance(cls) -> "GeoCoolingRuntime":
        """Retourne l'instance Runtime unique."""

        return cls()

    def register(
        self,
        name: str,
        component: Any,
    ) -> None:
        """Enregistre un composant sans remplacer silencieusement une instance."""

        if component is None:
            return

        normalized_name = str(name).strip()

        if not normalized_name:
            raise ValueError(
                "Le nom du composant Runtime est vide."
            )

        with self._lock:
            previous = self._components.get(
                normalized_name
            )

            self._registrations[normalized_name] = (
                self._registrations.get(
                    normalized_name,
                    0,
                )
                + 1
            )

            if previous is component:
                self._updated_at = utc_now_iso()
                return

            if previous is not None:
                self._conflicts.append(
                    {
                        "component": normalized_name,
                        "detected_at": utc_now_iso(),
                        "existing_type": (
                            f"{type(previous).__module__}."
                            f"{type(previous).__qualname__}"
                        ),
                        "new_type": (
                            f"{type(component).__module__}."
                            f"{type(component).__qualname__}"
                        ),
                        "existing_identity": id(previous),
                        "new_identity": id(component),
                    }
                )

                raise RuntimeError(
                    "Une autre instance est déjà enregistrée "
                    f"pour le composant {normalized_name!r}."
                )

            self._components[
                normalized_name
            ] = component

            self._updated_at = utc_now_iso()

    def register_many(
        self,
        **components: Any,
    ) -> None:
        for name, component in components.items():
            if component is not None:
                self.register(
                    name,
                    component,
                )

    def get(
        self,
        name: str,
        default: Any = None,
    ) -> Any:
        with self._lock:
            return self._components.get(
                name,
                default,
            )

    def require(
        self,
        name: str,
    ) -> Any:
        component = self.get(name)

        if component is None:
            raise RuntimeError(
                "Composant Runtime indisponible : "
                f"{name}"
            )

        return component

    def has(
        self,
        name: str,
    ) -> bool:
        with self._lock:
            return (
                name in self._components
                and self._components[name] is not None
            )

    @property
    def controller(self) -> Any:
        return self.require("controller")

    @property
    def health_manager(self) -> Any:
        return self.require("health_manager")

    @property
    def commissioning_manager(self) -> Any:
        return self.require(
            "commissioning_manager"
        )

    @property
    def commissioning_test_manager(self) -> Any:
        return self.require(
            "commissioning_test_manager"
        )

    @property
    def flight_recorder(self) -> Any:
        return self.require("flight_recorder")

    @property
    def event_timeline(self) -> Any:
        return self.require("event_timeline")

    @property
    def watchdog(self) -> Any:
        return self.require("watchdog")

    @staticmethod
    def _component_description(
        name: str,
        component: Any,
        registrations: int,
    ) -> dict[str, Any]:
        component_type = type(component)

        description = {
            "name": name,
            "available": True,
            "type": component_type.__name__,
            "qualified_type": (
                f"{component_type.__module__}."
                f"{component_type.__qualname__}"
            ),
            "identity": id(component),
            "registrations": registrations,
        }

        running = getattr(
            component,
            "running",
            None,
        )

        if isinstance(running, bool):
            description["running"] = running

        is_alive = getattr(
            component,
            "is_alive",
            None,
        )

        if callable(is_alive):
            try:
                description["thread_alive"] = bool(
                    is_alive()
                )
            except Exception as exc:
                description["thread_alive_error"] = str(
                    exc
                )

        return description

    def status(self) -> dict[str, Any]:
        """Retourne l'état structurel du Runtime sans appeler les services."""

        with self._lock:
            components = dict(
                self._components
            )

            registrations = dict(
                self._registrations
            )

            conflicts = list(
                self._conflicts
            )

        component_status: dict[
            str,
            dict[str, Any]
        ] = {}

        for name in self.EXPECTED_COMPONENTS:
            component = components.get(name)

            if component is None:
                component_status[name] = {
                    "name": name,
                    "available": False,
                    "registrations": (
                        registrations.get(
                            name,
                            0,
                        )
                    ),
                }
            else:
                component_status[name] = (
                    self._component_description(
                        name,
                        component,
                        registrations.get(
                            name,
                            0,
                        ),
                    )
                )

        additional_components = sorted(
            set(components)
            - set(self.EXPECTED_COMPONENTS)
        )

        for name in additional_components:
            component_status[name] = (
                self._component_description(
                    name,
                    components[name],
                    registrations.get(
                        name,
                        0,
                    ),
                )
            )

        missing = [
            name
            for name in self.EXPECTED_COMPONENTS
            if name not in components
        ]

        available = [
            name
            for name in self.EXPECTED_COMPONENTS
            if name in components
        ]

        if conflicts:
            overall = "CRITICAL"
        elif missing:
            overall = "DEGRADED"
        else:
            overall = "OK"

        controller = components.get(
            "controller"
        )

        controller_references: dict[
            str,
            bool | None
        ] = {}

        if controller is not None:
            reference_fields = {
                "health_manager": (
                    "controller",
                    "_controller",
                ),
                "commissioning_manager": (
                    "controller",
                    "_controller",
                ),
                "commissioning_test_manager": (
                    "controller",
                    "_controller",
                ),
                "flight_recorder": (
                    "controller",
                    "_controller",
                ),
                "event_timeline": (
                    "controller",
                    "_controller",
                ),
                "watchdog": (
                    "controller",
                    "_controller",
                ),
            }

            for component_name, attributes in (
                reference_fields.items()
            ):
                component = components.get(
                    component_name
                )

                if component is None:
                    controller_references[
                        component_name
                    ] = None
                    continue

                detected_reference = None

                for attribute in attributes:
                    if hasattr(
                        component,
                        attribute,
                    ):
                        detected_reference = (
                            getattr(
                                component,
                                attribute,
                                None,
                            )
                            is controller
                        )
                        break

                controller_references[
                    component_name
                ] = detected_reference

        inconsistent_references = [
            name
            for name, valid
            in controller_references.items()
            if valid is False
        ]

        if inconsistent_references:
            overall = "CRITICAL"

        return {
            "component": "geocooling",
            "view": "runtime",
            "generated_at": utc_now_iso(),
            "read_only": True,
            "singleton": True,
            "overall": overall,
            "runtime": {
                "created_at": self._created_at,
                "updated_at": self._updated_at,
                "identity": id(self),
                "expected_component_count": len(
                    self.EXPECTED_COMPONENTS
                ),
                "available_component_count": len(
                    available
                ),
                "missing_component_count": len(
                    missing
                ),
                "conflict_count": len(
                    conflicts
                ),
            },
            "available_components": available,
            "missing_components": missing,
            "additional_components": (
                additional_components
            ),
            "controller_references": (
                controller_references
            ),
            "inconsistent_controller_references": (
                inconsistent_references
            ),
            "components": component_status,
            "conflicts": conflicts,
        }
