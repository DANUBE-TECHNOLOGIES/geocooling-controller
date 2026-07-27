"""
C016.0R1 — Operational Certification Engine.

Autorité passive de certification de l'installation GeoCooling.

Ce composant :
- inspecte l'état réel du contrôleur ;
- évalue la disponibilité du matériel ;
- évalue les sondes et la sécurité thermique ;
- évalue le Brain et les composants d'analyse ;
- vérifie que le bridge reste désarmé ;
- publie un niveau de certification ;
- ne change jamais le driver ;
- n'arme jamais le bridge ;
- n'exécute aucune commande physique.
"""

from __future__ import annotations

import math
import threading
from collections import deque
from copy import deepcopy
from datetime import datetime, timezone
from typing import Any


class OperationalCertificationEngine:
    PATCH_VERSION = "C016.0R1"

    LEVELS = (
        "NOT_READY",
        "READY_FOR_SENSOR_TEST",
        "READY_FOR_MQTT_DRIVER",
        "READY_FOR_WATER_TEST",
        "READY_FOR_AUTOMATIC_CONTROL",
        "PRODUCTION_CERTIFIED",
    )

    LEVEL_RANK = {
        level: index
        for index, level in enumerate(LEVELS)
    }

    def __init__(
        self,
        *,
        controller: Any,
        event_bus: Any,
        controller_command_bridge: Any = None,
        execution_supervisor: Any = None,
        execution_analyzer: Any = None,
        thermal_performance_analyzer: Any = None,
        brain_feedback: Any = None,
        state_cache: Any = None,
        history_capacity: int = 500,
    ) -> None:
        self.controller = controller
        self.event_bus = event_bus

        self.controller_command_bridge = (
            controller_command_bridge
        )

        self.execution_supervisor = (
            execution_supervisor
        )

        self.execution_analyzer = (
            execution_analyzer
        )

        self.thermal_performance_analyzer = (
            thermal_performance_analyzer
        )

        self.brain_feedback = brain_feedback
        self.state_cache = state_cache

        self.history_capacity = max(
            50,
            int(history_capacity),
        )

        self._lock = threading.RLock()

        self._history: deque[dict[str, Any]] = deque(
            maxlen=self.history_capacity
        )

        self._started_at = self._utc_now()
        self._latest: dict[str, Any] | None = None

        self._metrics = {
            "evaluation_count": 0,
            "blocked_count": 0,
            "warning_count": 0,
            "production_certified_count": 0,
            "publish_error_count": 0,
            "last_evaluated_at": None,
            "last_level": None,
            "last_score": None,
            "last_error": None,
        }

    @staticmethod
    def _utc_now() -> str:
        return datetime.now(
            timezone.utc
        ).isoformat()

    @classmethod
    def _safe(
        cls,
        value: Any,
        *,
        depth: int = 0,
        seen: set[int] | None = None,
    ) -> Any:
        if depth > 8:
            return "<max-depth>"

        if seen is None:
            seen = set()

        if value is None or isinstance(
            value,
            (bool, int, float, str),
        ):
            if isinstance(value, float):
                if math.isnan(value) or math.isinf(value):
                    return None

            return value

        object_id = id(value)

        if object_id in seen:
            return "<recursive-reference>"

        seen.add(object_id)

        try:
            if isinstance(value, dict):
                return {
                    str(key): cls._safe(
                        item,
                        depth=depth + 1,
                        seen=seen,
                    )
                    for key, item in value.items()
                }

            if isinstance(value, (list, tuple, set)):
                return [
                    cls._safe(
                        item,
                        depth=depth + 1,
                        seen=seen,
                    )
                    for item in value
                ]

            enum_value = getattr(
                value,
                "value",
                None,
            )

            if isinstance(
                enum_value,
                (bool, int, float, str),
            ):
                return enum_value

            isoformat = getattr(
                value,
                "isoformat",
                None,
            )

            if callable(isoformat):
                try:
                    return isoformat()
                except Exception:
                    pass

            return repr(value)

        finally:
            seen.discard(object_id)

    @staticmethod
    def _call(
        obj: Any,
        method_name: str,
        *args: Any,
        **kwargs: Any,
    ) -> dict[str, Any]:
        if obj is None:
            return {
                "available": False,
                "reason": "component_absent",
                "result": None,
            }

        method = getattr(
            obj,
            method_name,
            None,
        )

        if not callable(method):
            return {
                "available": False,
                "reason": "method_absent",
                "result": None,
            }

        try:
            result = method(
                *args,
                **kwargs,
            )

            return {
                "available": True,
                "reason": None,
                "result": result,
            }

        except Exception as exc:
            return {
                "available": False,
                "reason": "method_error",
                "error": repr(exc),
                "result": None,
            }

    @staticmethod
    def _dict(
        value: Any,
    ) -> dict[str, Any]:
        return value if isinstance(value, dict) else {}

    @staticmethod
    def _bool(
        value: Any,
        default: bool = False,
    ) -> bool:
        if isinstance(value, bool):
            return value

        if isinstance(value, (int, float)):
            return bool(value)

        if isinstance(value, str):
            return value.strip().lower() in {
                "true",
                "yes",
                "1",
                "on",
                "ready",
                "healthy",
                "ok",
                "safe",
                "running",
                "connected",
                "online",
            }

        return default

    @staticmethod
    def _number(
        value: Any,
    ) -> float | None:
        if value is None or isinstance(value, bool):
            return None

        try:
            result = float(value)
        except (TypeError, ValueError):
            return None

        if math.isnan(result) or math.isinf(result):
            return None

        return result

    def _component_status(
        self,
        component: Any,
    ) -> dict[str, Any]:
        for method_name in (
            "status",
            "metrics",
            "latest",
            "current",
            "diagnostics",
        ):
            response = self._call(
                component,
                method_name,
            )

            if response["available"]:
                return {
                    "available": True,
                    "method": method_name,
                    "result": self._safe(
                        response["result"]
                    ),
                }

        return {
            "available": component is not None,
            "method": None,
            "result": None,
        }

    @staticmethod
    def _check(
        *,
        check_id: str,
        category: str,
        description: str,
        passed: bool,
        blocking_level: str,
        observed: Any = None,
        expected: Any = None,
        mandatory: bool = True,
        remediation: str | None = None,
    ) -> dict[str, Any]:
        return {
            "id": check_id,
            "category": category,
            "description": description,
            "passed": bool(passed),
            "mandatory": bool(mandatory),
            "blocking_level": blocking_level,
            "observed": observed,
            "expected": expected,
            "remediation": remediation,
        }

    def _add_controller_checks(
        self,
        checks: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> None:
        state = str(
            controller_status.get(
                "state",
                "",
            )
        ).upper()

        mode = str(
            controller_status.get(
                "mode",
                "",
            )
        ).upper()

        simulation = self._bool(
            controller_status.get("simulation")
        )

        last_error = controller_status.get(
            "last_error"
        )

        checks.append(
            self._check(
                check_id="controller.status.available",
                category="controller",
                description=(
                    "Le statut global du contrôleur "
                    "est disponible."
                ),
                passed=bool(controller_status),
                blocking_level="READY_FOR_SENSOR_TEST",
                observed=bool(controller_status),
                expected=True,
                remediation=(
                    "Vérifier l'initialisation du "
                    "GeoCoolingController."
                ),
            )
        )

        checks.append(
            self._check(
                check_id="controller.no_error",
                category="controller",
                description=(
                    "Le contrôleur ne signale aucune "
                    "erreur active."
                ),
                passed=last_error in {
                    None,
                    "",
                },
                blocking_level="READY_FOR_SENSOR_TEST",
                observed=last_error,
                expected=None,
                remediation=(
                    "Corriger last_error avant toute "
                    "mise en service."
                ),
            )
        )

        checks.append(
            self._check(
                check_id="controller.safe_state",
                category="controller",
                description=(
                    "Le contrôleur est dans un état sûr "
                    "pendant la certification."
                ),
                passed=state in {
                    "OFF",
                    "IDLE",
                    "STOPPED",
                },
                blocking_level="READY_FOR_MQTT_DRIVER",
                observed=state,
                expected="OFF",
                remediation=(
                    "Arrêter complètement le cycle avant "
                    "la certification."
                ),
            )
        )

        checks.append(
            self._check(
                check_id="controller.simulation_known",
                category="controller",
                description=(
                    "Le mode de fonctionnement est "
                    "clairement identifié."
                ),
                passed=mode in {
                    "SIMULATION",
                    "MQTT",
                    "PRODUCTION",
                    "HARDWARE",
                },
                blocking_level="READY_FOR_SENSOR_TEST",
                observed={
                    "mode": mode,
                    "simulation": simulation,
                },
                expected=(
                    "SIMULATION ou mode matériel reconnu"
                ),
                remediation=(
                    "Configurer explicitement le mode "
                    "du contrôleur."
                ),
            )
        )

    def _add_device_checks(
        self,
        checks: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> None:
        device = self._dict(
            controller_status.get("device")
        )

        ready = self._bool(
            device.get("ready")
        )

        connected = self._bool(
            device.get("connected")
        )

        online = self._bool(
            device.get("online")
        )

        heartbeat_fresh = self._bool(
            device.get("heartbeat_fresh")
        )

        simulation = self._bool(
            device.get("simulation")
        )

        checks.extend(
            [
                self._check(
                    check_id="device.present",
                    category="device",
                    description=(
                        "Le DeviceManager expose un statut."
                    ),
                    passed=bool(device),
                    blocking_level="READY_FOR_SENSOR_TEST",
                    observed=bool(device),
                    expected=True,
                    remediation=(
                        "Vérifier le DeviceManager et "
                        "le driver actif."
                    ),
                ),
                self._check(
                    check_id="device.ready",
                    category="device",
                    description=(
                        "Le DeviceManager est prêt."
                    ),
                    passed=ready,
                    blocking_level="READY_FOR_SENSOR_TEST",
                    observed=ready,
                    expected=True,
                    remediation=(
                        "Corriger le driver ou la "
                        "communication matérielle."
                    ),
                ),
                self._check(
                    check_id="device.connected",
                    category="device",
                    description=(
                        "Le périphérique est connecté."
                    ),
                    passed=connected,
                    blocking_level="READY_FOR_MQTT_DRIVER",
                    observed=connected,
                    expected=True,
                    remediation=(
                        "Vérifier Ethernet, MQTT, alimentation "
                        "et configuration du relais."
                    ),
                ),
                self._check(
                    check_id="device.online",
                    category="device",
                    description=(
                        "Le périphérique est déclaré en ligne."
                    ),
                    passed=online,
                    blocking_level="READY_FOR_MQTT_DRIVER",
                    observed=online,
                    expected=True,
                    remediation=(
                        "Vérifier les messages d'état "
                        "et le topic MQTT."
                    ),
                ),
                self._check(
                    check_id="device.heartbeat_fresh",
                    category="device",
                    description=(
                        "Le heartbeat du périphérique "
                        "est récent."
                    ),
                    passed=heartbeat_fresh,
                    blocking_level="READY_FOR_WATER_TEST",
                    observed=heartbeat_fresh,
                    expected=True,
                    remediation=(
                        "Rétablir le heartbeat avant "
                        "les essais hydrauliques."
                    ),
                ),
                self._check(
                    check_id="device.real_hardware",
                    category="device",
                    description=(
                        "Le driver actif correspond à du "
                        "matériel réel et non à la simulation."
                    ),
                    passed=not simulation,
                    blocking_level="READY_FOR_WATER_TEST",
                    observed={
                        "simulation": simulation,
                        "driver": device.get("driver"),
                    },
                    expected={
                        "simulation": False,
                    },
                    mandatory=True,
                    remediation=(
                        "Installer et valider le driver MQTT "
                        "avant les essais hydrauliques."
                    ),
                ),
            ]
        )

    def _add_bridge_checks(
        self,
        checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        bridge_status_response = self._call(
            self.controller_command_bridge,
            "status",
        )

        bridge_status = self._dict(
            bridge_status_response.get(
                "result"
            )
        )

        armed = self._bool(
            bridge_status.get("armed")
        )

        checks.append(
            self._check(
                check_id="bridge.available",
                category="bridge",
                description=(
                    "Le ControllerCommandBridge "
                    "est disponible."
                ),
                passed=bridge_status_response[
                    "available"
                ],
                blocking_level="READY_FOR_MQTT_DRIVER",
                observed=(
                    bridge_status_response[
                        "available"
                    ]
                ),
                expected=True,
                remediation=(
                    "Restaurer le bridge de commandes."
                ),
            )
        )

        checks.append(
            self._check(
                check_id="bridge.disarmed",
                category="bridge",
                description=(
                    "Le bridge reste désarmé pendant "
                    "la certification."
                ),
                passed=not armed,
                blocking_level="PRODUCTION_CERTIFIED",
                observed=armed,
                expected=False,
                remediation=(
                    "Désarmer immédiatement le bridge."
                ),
            )
        )

        return bridge_status

    def _add_safety_checks(
        self,
        checks: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> None:
        safety = self._dict(
            controller_status.get("safety")
        )

        safe = self._bool(
            safety.get("safe")
        )

        level = str(
            safety.get(
                "level",
                "",
            )
        ).lower()

        measurements_available = level not in {
            "",
            "unavailable",
            "unknown",
        }

        checks.append(
            self._check(
                check_id="safety.safe",
                category="safety",
                description=(
                    "La sécurité thermique ne signale "
                    "aucun danger."
                ),
                passed=safe,
                blocking_level="READY_FOR_SENSOR_TEST",
                observed=safety,
                expected={
                    "safe": True,
                },
                remediation=(
                    "Corriger la marge au point de rosée "
                    "avant tout essai."
                ),
            )
        )

        checks.append(
            self._check(
                check_id="safety.measurements_available",
                category="safety",
                description=(
                    "La décision de sécurité repose sur "
                    "des mesures thermiques réelles."
                ),
                passed=measurements_available,
                blocking_level="READY_FOR_WATER_TEST",
                observed={
                    "level": level,
                    "dew_point_c": safety.get(
                        "dew_point_c"
                    ),
                    "surface_temperature_c": safety.get(
                        "surface_temperature_c"
                    ),
                    "margin_c": safety.get(
                        "margin_c"
                    ),
                },
                expected=(
                    "Niveau de sécurité disponible avec "
                    "point de rosée et température de surface"
                ),
                remediation=(
                    "Connecter les sondes d'ambiance, "
                    "d'humidité et de surface."
                ),
            )
        )

        margin = self._number(
            safety.get("margin_c")
        )

        minimum_margin = self._number(
            self._dict(
                controller_status.get(
                    "configuration"
                )
            ).get(
                "minimum_dew_point_margin_c"
            )
        )

        if minimum_margin is None:
            minimum_margin = 3.0

        margin_passed = (
            margin is not None
            and margin >= minimum_margin
        )

        checks.append(
            self._check(
                check_id="safety.dew_point_margin",
                category="safety",
                description=(
                    "La marge au-dessus du point de rosée "
                    "est suffisante."
                ),
                passed=margin_passed,
                blocking_level="READY_FOR_AUTOMATIC_CONTROL",
                observed=margin,
                expected=f">= {minimum_margin} °C",
                remediation=(
                    "Augmenter la température minimale "
                    "de surface ou réduire le refroidissement."
                ),
            )
        )

    def _add_thermal_checks(
        self,
        checks: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> None:
        thermal = self._dict(
            controller_status.get("thermal")
        )

        available = self._bool(
            thermal.get("available")
        )

        history_count = int(
            self._number(
                thermal.get("history_count")
            )
            or 0
        )

        checks.extend(
            [
                self._check(
                    check_id="thermal.engine_available",
                    category="thermal",
                    description=(
                        "Le moteur thermique est accessible."
                    ),
                    passed=bool(thermal),
                    blocking_level="READY_FOR_SENSOR_TEST",
                    observed=bool(thermal),
                    expected=True,
                    remediation=(
                        "Vérifier l'initialisation du "
                        "ThermalEngine."
                    ),
                ),
                self._check(
                    check_id="thermal.measurement_available",
                    category="thermal",
                    description=(
                        "Une mesure thermique exploitable "
                        "est disponible."
                    ),
                    passed=available,
                    blocking_level="READY_FOR_WATER_TEST",
                    observed=thermal,
                    expected={
                        "available": True,
                    },
                    remediation=(
                        "Publier une trame thermique complète "
                        "depuis le WT32."
                    ),
                ),
                self._check(
                    check_id="thermal.history",
                    category="thermal",
                    description=(
                        "Un historique thermique minimal "
                        "est disponible."
                    ),
                    passed=history_count >= 5,
                    blocking_level="READY_FOR_AUTOMATIC_CONTROL",
                    observed=history_count,
                    expected=">= 5 mesures",
                    remediation=(
                        "Accumuler plusieurs mesures "
                        "thermiques cohérentes."
                    ),
                ),
            ]
        )

    def _add_brain_checks(
        self,
        checks: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> None:
        brain = self._dict(
            controller_status.get("brain")
        )

        decision = str(
            brain.get(
                "decision",
                "",
            )
        ).upper()

        confidence = self._number(
            brain.get("confidence")
        )

        data_quality = self._number(
            brain.get("data_quality")
        )

        operating_mode = str(
            brain.get(
                "operating_mode",
                "",
            )
        ).upper()

        configuration = self._dict(
            brain.get("configuration")
        )

        advisory_only = self._bool(
            configuration.get(
                "advisory_only",
                True,
            )
        )

        state_cache = self._dict(
            brain.get("state_cache")
        )

        state_cache_ready = self._bool(
            state_cache.get("ready")
        )

        state_cache_running = self._bool(
            state_cache.get("running")
        )

        state_cache_stale = self._bool(
            state_cache.get("stale")
        )

        checks.extend(
            [
                self._check(
                    check_id="brain.available",
                    category="brain",
                    description=(
                        "Le Brain produit une décision."
                    ),
                    passed=bool(brain) and bool(decision),
                    blocking_level="READY_FOR_SENSOR_TEST",
                    observed=decision,
                    expected=(
                        "WAIT, START, STOP ou "
                        "EMERGENCY_STOP"
                    ),
                    remediation=(
                        "Vérifier l'initialisation du Brain."
                    ),
                ),
                self._check(
                    check_id="brain.advisory_only",
                    category="brain",
                    description=(
                        "Le Brain reste en mode conseil "
                        "pendant les validations."
                    ),
                    passed=advisory_only,
                    blocking_level="PRODUCTION_CERTIFIED",
                    observed=advisory_only,
                    expected=True,
                    remediation=(
                        "Réactiver advisory_only avant "
                        "toute certification."
                    ),
                ),
                self._check(
                    check_id="brain.state_cache_ready",
                    category="brain",
                    description=(
                        "Le StateCache est prêt, actif "
                        "et non périmé."
                    ),
                    passed=(
                        state_cache_ready
                        and state_cache_running
                        and not state_cache_stale
                    ),
                    blocking_level="READY_FOR_MQTT_DRIVER",
                    observed=state_cache,
                    expected={
                        "ready": True,
                        "running": True,
                        "stale": False,
                    },
                    remediation=(
                        "Rétablir les snapshots et "
                        "le StateCache."
                    ),
                ),
                self._check(
                    check_id="brain.data_quality",
                    category="brain",
                    description=(
                        "La qualité des données du Brain "
                        "est suffisante."
                    ),
                    passed=(
                        data_quality is not None
                        and data_quality >= 70
                    ),
                    blocking_level="READY_FOR_AUTOMATIC_CONTROL",
                    observed=data_quality,
                    expected=">= 70",
                    remediation=(
                        "Compléter les températures, "
                        "l'humidité et les mesures hydrauliques."
                    ),
                ),
                self._check(
                    check_id="brain.confidence",
                    category="brain",
                    description=(
                        "La confiance du Brain est suffisante."
                    ),
                    passed=(
                        confidence is not None
                        and confidence >= 70
                        and operating_mode != "DEGRADED"
                    ),
                    blocking_level="READY_FOR_AUTOMATIC_CONTROL",
                    observed={
                        "confidence": confidence,
                        "operating_mode": operating_mode,
                    },
                    expected={
                        "confidence": ">= 70",
                        "operating_mode": (
                            "non DEGRADED"
                        ),
                    },
                    remediation=(
                        "Améliorer les données avant "
                        "l'automatisation."
                    ),
                ),
            ]
        )

    def _add_analysis_checks(
        self,
        checks: list[dict[str, Any]],
    ) -> dict[str, Any]:
        components = {
            "execution_supervisor":
                self.execution_supervisor,
            "execution_analyzer":
                self.execution_analyzer,
            "thermal_performance_analyzer":
                self.thermal_performance_analyzer,
            "brain_feedback":
                self.brain_feedback,
        }

        results: dict[str, Any] = {}

        for name, component in components.items():
            status = self._component_status(
                component
            )

            results[name] = status

            checks.append(
                self._check(
                    check_id=f"analysis.{name}.available",
                    category="analysis",
                    description=(
                        f"Le composant {name} "
                        "est disponible."
                    ),
                    passed=status["available"],
                    blocking_level=(
                        "READY_FOR_AUTOMATIC_CONTROL"
                    ),
                    observed=status["available"],
                    expected=True,
                    remediation=(
                        f"Restaurer ou initialiser {name}."
                    ),
                )
            )

        thermal_latest = self._call(
            self.thermal_performance_analyzer,
            "latest",
        )

        thermal_latest_result = self._dict(
            thermal_latest.get("result")
        )

        thermal_performance_available = (
            thermal_latest["available"]
            and self._bool(
                thermal_latest_result.get(
                    "available"
                )
            )
        )

        checks.append(
            self._check(
                check_id=(
                    "analysis.thermal_performance.available"
                ),
                category="analysis",
                description=(
                    "Une analyse de performance thermique "
                    "réelle est disponible."
                ),
                passed=thermal_performance_available,
                blocking_level="READY_FOR_AUTOMATIC_CONTROL",
                observed=thermal_latest_result,
                expected={
                    "available": True,
                },
                remediation=(
                    "Réaliser au moins un cycle thermique "
                    "mesuré et analysé."
                ),
            )
        )

        feedback_latest = self._call(
            self.brain_feedback,
            "latest",
        )

        feedback_latest_result = self._dict(
            feedback_latest.get("result")
        )

        feedback_available = (
            feedback_latest["available"]
            and self._bool(
                feedback_latest_result.get(
                    "available"
                )
            )
        )

        checks.append(
            self._check(
                check_id="analysis.feedback.available",
                category="analysis",
                description=(
                    "Un retour d'apprentissage "
                    "est disponible."
                ),
                passed=feedback_available,
                blocking_level="PRODUCTION_CERTIFIED",
                observed=feedback_latest_result,
                expected={
                    "available": True,
                },
                remediation=(
                    "Accumuler et analyser plusieurs "
                    "cycles réels."
                ),
            )
        )

        return results

    def _determine_level(
        self,
        checks: list[dict[str, Any]],
    ) -> str:
        level = "PRODUCTION_CERTIFIED"

        for candidate in self.LEVELS[1:]:
            required_checks = [
                check
                for check in checks
                if (
                    check["mandatory"]
                    and self.LEVEL_RANK[
                        check["blocking_level"]
                    ]
                    <= self.LEVEL_RANK[candidate]
                )
            ]

            if not all(
                check["passed"]
                for check in required_checks
            ):
                previous_rank = max(
                    0,
                    self.LEVEL_RANK[candidate] - 1,
                )

                level = self.LEVELS[
                    previous_rank
                ]

                break

        if not all(
            check["passed"]
            for check in checks
            if (
                check["mandatory"]
                and check["blocking_level"]
                == "READY_FOR_SENSOR_TEST"
            )
        ):
            level = "NOT_READY"

        return level

    def _score(
        self,
        checks: list[dict[str, Any]],
    ) -> int:
        mandatory = [
            check
            for check in checks
            if check["mandatory"]
        ]

        if not mandatory:
            return 0

        passed = sum(
            1
            for check in mandatory
            if check["passed"]
        )

        return round(
            passed
            / len(mandatory)
            * 100
        )

    def _publish(
        self,
        event_type: str,
        payload: dict[str, Any],
        level: str,
    ) -> None:
        try:
            self.event_bus.publish(
                event_type=event_type,
                source="operational-certification",
                payload=self._safe(payload),
                level=level,
            )

            with self._lock:
                self._metrics["last_error"] = None

        except Exception as exc:
            with self._lock:
                self._metrics[
                    "publish_error_count"
                ] += 1

                self._metrics[
                    "last_error"
                ] = repr(exc)

    def evaluate(
        self,
        *,
        trigger: str = "manual",
    ) -> dict[str, Any]:
        generated_at = self._utc_now()

        controller_response = self._call(
            self.controller,
            "status",
        )

        controller_status = self._dict(
            controller_response.get(
                "result"
            )
        )

        checks: list[dict[str, Any]] = []

        self._add_controller_checks(
            checks,
            controller_status,
        )

        self._add_device_checks(
            checks,
            controller_status,
        )

        bridge_status = self._add_bridge_checks(
            checks
        )

        self._add_safety_checks(
            checks,
            controller_status,
        )

        self._add_thermal_checks(
            checks,
            controller_status,
        )

        self._add_brain_checks(
            checks,
            controller_status,
        )

        analysis_components = (
            self._add_analysis_checks(
                checks
            )
        )

        level = self._determine_level(
            checks
        )

        score = self._score(
            checks
        )

        failed_checks = [
            check
            for check in checks
            if not check["passed"]
        ]

        blockers = [
            check
            for check in failed_checks
            if check["mandatory"]
        ]

        warnings = [
            check
            for check in failed_checks
            if not check["mandatory"]
        ]

        mode = str(
            controller_status.get(
                "mode",
                "",
            )
        ).upper()

        simulation = self._bool(
            controller_status.get("simulation")
        )

        certification = {
            "certification_id": (
                f"certification:{generated_at}"
            ),
            "generated_at": generated_at,
            "trigger": trigger,
            "patch_version": self.PATCH_VERSION,
            "level": level,
            "score": score,
            "ready": level != "NOT_READY",
            "production_certified": (
                level == "PRODUCTION_CERTIFIED"
            ),
            "automatic_bridge_arm_allowed": False,
            "manual_bridge_arm_required": True,
            "bridge_armed": self._bool(
                bridge_status.get("armed")
            ),
            "mode": mode,
            "simulation": simulation,
            "check_count": len(checks),
            "passed_count": sum(
                1
                for check in checks
                if check["passed"]
            ),
            "failed_count": len(failed_checks),
            "blocking_count": len(blockers),
            "warning_count": len(warnings),
            "checks": checks,
            "blockers": blockers,
            "warnings": warnings,
            "next_level": self._next_level(
                level
            ),
            "next_actions": self._next_actions(
                level,
                blockers,
            ),
            "controller": self._safe(
                controller_status
            ),
            "analysis_components": (
                analysis_components
            ),
        }

        with self._lock:
            self._latest = deepcopy(
                certification
            )

            self._history.append(
                deepcopy(certification)
            )

            self._metrics[
                "evaluation_count"
            ] += 1

            self._metrics[
                "blocked_count"
            ] += int(bool(blockers))

            self._metrics[
                "warning_count"
            ] += len(warnings)

            if certification[
                "production_certified"
            ]:
                self._metrics[
                    "production_certified_count"
                ] += 1

            self._metrics[
                "last_evaluated_at"
            ] = generated_at

            self._metrics[
                "last_level"
            ] = level

            self._metrics[
                "last_score"
            ] = score

        if level == "NOT_READY":
            event_type = (
                "system.certification.blocked"
            )
            event_level = "ERROR"

        elif blockers:
            event_type = (
                "system.certification.warning"
            )
            event_level = "WARN"

        else:
            event_type = "system.certification"
            event_level = "INFO"

        self._publish(
            event_type,
            certification,
            event_level,
        )

        self._publish(
            "system.certification",
            certification,
            (
                "INFO"
                if level != "NOT_READY"
                else "WARN"
            ),
        )

        return deepcopy(certification)

    def _next_level(
        self,
        current_level: str,
    ) -> str | None:
        rank = self.LEVEL_RANK.get(
            current_level,
            0,
        )

        if rank >= len(self.LEVELS) - 1:
            return None

        return self.LEVELS[
            rank + 1
        ]

    @staticmethod
    def _next_actions(
        level: str,
        blockers: list[dict[str, Any]],
    ) -> list[str]:
        actions: list[str] = []

        for check in blockers:
            remediation = check.get(
                "remediation"
            )

            if (
                remediation
                and remediation not in actions
            ):
                actions.append(remediation)

        if not actions:
            if level == "PRODUCTION_CERTIFIED":
                actions.append(
                    "Une validation humaine explicite reste "
                    "obligatoire avant l'armement du bridge."
                )
            else:
                actions.append(
                    "Aucune action complémentaire détectée."
                )

        return actions[:20]

    def status(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(
                self._latest
            )

            metrics = deepcopy(
                self._metrics
            )

        return {
            "overall": "OK",
            "component": (
                "operational_certification"
            ),
            "patch_version": self.PATCH_VERSION,
            "running": True,
            "started_at": self._started_at,
            "levels": list(self.LEVELS),
            "automatic_bridge_arm_allowed": False,
            "history_count": len(
                self._history
            ),
            "latest_level": (
                latest.get("level")
                if latest
                else None
            ),
            "latest_score": (
                latest.get("score")
                if latest
                else None
            ),
            "metrics": metrics,
        }

    def latest(self) -> dict[str, Any]:
        with self._lock:
            latest = deepcopy(
                self._latest
            )

        return {
            "overall": "OK",
            "component": (
                "operational_certification"
            ),
            "available": latest is not None,
            "certification": latest,
        }

    def history(
        self,
        *,
        limit: int = 100,
    ) -> dict[str, Any]:
        limit = max(
            1,
            min(
                int(limit),
                self.history_capacity,
            ),
        )

        with self._lock:
            items = list(
                self._history
            )[-limit:]

        return {
            "overall": "OK",
            "component": (
                "operational_certification"
            ),
            "count": len(items),
            "limit": limit,
            "certifications": deepcopy(
                items
            ),
        }
