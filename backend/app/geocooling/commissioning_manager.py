"""Assistant de mise en service du sous-système GeoCooling.

Ce module est strictement en lecture seule.

Il transforme les informations techniques du Health Manager et du Controller
en une checklist lisible pendant le raccordement du matériel.

Il ne doit jamais :

- activer une pompe ;
- activer une vanne ;
- publier une commande MQTT ;
- modifier un mode ;
- changer l'état du Controller ;
- exécuter une commande manuelle ;
- décider à la place du Brain.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any


def utc_now_iso() -> str:
    """Retourne l'heure courante au format ISO UTC."""

    return datetime.now(timezone.utc).isoformat()


class GeoCoolingCommissioningManager:
    """Construit la checklist de mise en service GeoCooling."""

    def __init__(
        self,
        controller: Any,
        health_manager: Any,
    ) -> None:
        self.controller = controller
        self.health_manager = health_manager

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    @staticmethod
    def _check(
        *,
        key: str,
        label: str,
        status: str,
        required: bool,
        message: str,
        details: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        normalized_status = str(status).upper()

        if normalized_status not in {
            "PASS",
            "WARNING",
            "FAIL",
            "NOT_APPLICABLE",
        }:
            normalized_status = "FAIL"

        return {
            "key": key,
            "label": label,
            "status": normalized_status,
            "required": required,
            "message": message,
            "details": details or {},
        }

    @staticmethod
    def _health_to_check_status(
        health_status: Any,
    ) -> str:
        value = str(health_status or "ERROR").upper()

        if value == "OK":
            return "PASS"

        if value == "WARNING":
            return "WARNING"

        return "FAIL"

    def _safe_controller_status(
        self,
    ) -> tuple[dict[str, Any], str | None]:
        try:
            result = self.controller.status()

            if not isinstance(result, dict):
                raise TypeError(
                    "controller.status() n'a pas retourné "
                    "un dictionnaire."
                )

            return result, None

        except Exception as exc:
            return {}, str(exc)

    def _safe_health_status(
        self,
    ) -> tuple[dict[str, Any], str | None]:
        try:
            result = self.health_manager.status()

            if not isinstance(result, dict):
                raise TypeError(
                    "health_manager.status() n'a pas retourné "
                    "un dictionnaire."
                )

            return result, None

        except Exception as exc:
            return {}, str(exc)

    def _build_database_check(
        self,
        components: dict[str, Any],
    ) -> dict[str, Any]:
        database = self._mapping(
            components.get("database")
        )

        return self._check(
            key="database",
            label="PostgreSQL",
            status=self._health_to_check_status(
                database.get("status")
            ),
            required=True,
            message=str(
                database.get(
                    "message",
                    "État PostgreSQL indisponible.",
                )
            ),
            details={
                "error": database.get("error"),
            },
        )

    def _build_controller_check(
        self,
        components: dict[str, Any],
    ) -> dict[str, Any]:
        controller = self._mapping(
            components.get("controller")
        )

        return self._check(
            key="controller",
            label="GeoCooling Controller",
            status=self._health_to_check_status(
                controller.get("status")
            ),
            required=True,
            message=str(
                controller.get(
                    "message",
                    "État Controller indisponible.",
                )
            ),
            details={
                "state": controller.get("state"),
                "mode": controller.get("mode"),
                "simulation": controller.get(
                    "simulation"
                ),
                "last_event": controller.get(
                    "last_event"
                ),
                "last_reason": controller.get(
                    "last_reason"
                ),
                "last_error": controller.get(
                    "last_error"
                ),
            },
        )

    def _build_brain_check(
        self,
        components: dict[str, Any],
    ) -> dict[str, Any]:
        brain = self._mapping(
            components.get("brain")
        )

        return self._check(
            key="brain",
            label="GeoCooling Brain",
            status=self._health_to_check_status(
                brain.get("status")
            ),
            required=True,
            message=str(
                brain.get(
                    "message",
                    "État Brain indisponible.",
                )
            ),
            details={
                "decision": brain.get("decision"),
                "confidence": brain.get(
                    "confidence"
                ),
                "data_quality": brain.get(
                    "data_quality"
                ),
                "operating_mode": brain.get(
                    "operating_mode"
                ),
                "generated_at": brain.get(
                    "generated_at"
                ),
                "age_seconds": brain.get(
                    "age_seconds"
                ),
                "reason": brain.get("reason"),
            },
        )

    def _build_driver_check(
        self,
        components: dict[str, Any],
        simulation: bool,
    ) -> dict[str, Any]:
        driver = self._mapping(
            components.get("driver")
        )

        if simulation:
            status = "WARNING"
            message = (
                "Le Driver fonctionne en simulation. "
                "Le raccordement MQTT réel reste à valider."
            )
        else:
            status = self._health_to_check_status(
                driver.get("status")
            )
            message = str(
                driver.get(
                    "message",
                    "État Driver indisponible.",
                )
            )

        return self._check(
            key="mqtt_driver",
            label="Driver MQTT",
            status=status,
            required=True,
            message=message,
            details={
                "name": driver.get("name"),
                "simulation": driver.get(
                    "simulation"
                ),
                "connected": driver.get(
                    "connected"
                ),
                "last_message_at": driver.get(
                    "last_message_at"
                ),
                "last_message_age_seconds": (
                    driver.get(
                        "last_message_age_seconds"
                    )
                ),
                "last_error": driver.get(
                    "last_error"
                ),
            },
        )

    def _build_esp_check(
        self,
        components: dict[str, Any],
        simulation: bool,
    ) -> dict[str, Any]:
        device = self._mapping(
            components.get("device")
        )

        driver = self._mapping(
            components.get("driver")
        )

        if simulation:
            status = "WARNING"
            message = (
                "ESP32 simulé. Le heartbeat réel devra être "
                "contrôlé après raccordement."
            )
        else:
            status = self._health_to_check_status(
                device.get("status")
            )
            message = str(
                device.get(
                    "message",
                    "État ESP32 indisponible.",
                )
            )

        return self._check(
            key="esp32",
            label="ESP32 / WT32-ETH01",
            status=status,
            required=True,
            message=message,
            details={
                "ready": device.get("ready"),
                "connected": device.get(
                    "connected"
                ),
                "online": device.get("online"),
                "heartbeat_fresh": device.get(
                    "heartbeat_fresh"
                ),
                "heartbeat_age_seconds": (
                    driver.get(
                        "heartbeat_age_seconds"
                    )
                ),
                "heartbeat_timeout_seconds": (
                    driver.get(
                        "heartbeat_timeout_seconds"
                    )
                ),
                "last_heartbeat_at": driver.get(
                    "last_heartbeat_at"
                ),
            },
        )

    def _build_thermal_check(
        self,
        components: dict[str, Any],
        simulation: bool,
    ) -> dict[str, Any]:
        thermal = self._mapping(
            components.get("thermal")
        )

        invalid = thermal.get("invalid") or []
        detected = thermal.get("detected") or []
        missing = thermal.get("missing") or []

        if invalid:
            status = "FAIL"
            message = (
                "Une ou plusieurs mesures thermiques "
                "sont invalides."
            )

        elif thermal.get("stale"):
            status = "WARNING"
            message = (
                "Les mesures thermiques ne sont pas "
                "suffisamment récentes."
            )

        elif not thermal.get("available"):
            status = "WARNING"
            message = (
                "Les mesures thermiques sont "
                "incomplètes ou absentes."
            )

        elif simulation:
            status = "WARNING"
            message = (
                "Les mesures thermiques sont simulées. "
                "Les sondes physiques restent à valider."
            )

        else:
            status = self._health_to_check_status(
                thermal.get("status")
            )
            message = str(
                thermal.get(
                    "message",
                    "État thermique indisponible.",
                )
            )

        return self._check(
            key="thermal_sensors",
            label="Sondes et mesures thermiques",
            status=status,
            required=True,
            message=message,
            details={
                "available": thermal.get(
                    "available"
                ),
                "timestamp": thermal.get(
                    "timestamp"
                ),
                "age_seconds": thermal.get(
                    "age_seconds"
                ),
                "stale": thermal.get("stale"),
                "stale_after_seconds": (
                    thermal.get(
                        "stale_after_seconds"
                    )
                ),
                "detected_count": thermal.get(
                    "detected_count"
                ),
                "detected": detected,
                "missing": missing,
                "invalid": invalid,
                "values": thermal.get(
                    "values",
                    {},
                ),
            },
        )

    def _build_safety_check(
        self,
        components: dict[str, Any],
    ) -> dict[str, Any]:
        safety = self._mapping(
            components.get("safety")
        )

        return self._check(
            key="thermal_safety",
            label="Sécurité thermique",
            status=self._health_to_check_status(
                safety.get("status")
            ),
            required=True,
            message=str(
                safety.get(
                    "message",
                    "État Safety indisponible.",
                )
            ),
            details={
                "safe": safety.get("safe"),
                "level": safety.get("level"),
                "dew_point_c": safety.get(
                    "dew_point_c"
                ),
                "surface_temperature_c": (
                    safety.get(
                        "surface_temperature_c"
                    )
                ),
                "margin_c": safety.get(
                    "margin_c"
                ),
            },
        )

    def _build_actuator_observation(
        self,
        components: dict[str, Any],
        simulation: bool,
    ) -> dict[str, Any]:
        driver = self._mapping(
            components.get("driver")
        )

        pump_running = bool(
            driver.get(
                "pump_running",
                False,
            )
        )

        valve_open = bool(
            driver.get(
                "valve_open",
                False,
            )
        )

        if pump_running or valve_open:
            status = "WARNING"
            message = (
                "Un actionneur est actuellement signalé actif. "
                "Vérifier l'installation avant toute intervention."
            )
        else:
            status = "PASS"
            message = (
                "Pompe et vanne signalées à l'arrêt."
            )

        return self._check(
            key="actuator_observation",
            label="État observé des actionneurs",
            status=status,
            required=True,
            message=message,
            details={
                "read_only": True,
                "simulation": simulation,
                "pump_running": pump_running,
                "valve_open": valve_open,
                "last_action_at": driver.get(
                    "last_action_at"
                ),
            },
        )

    def _build_manual_pipeline_check(
        self,
        controller_status: dict[str, Any],
    ) -> dict[str, Any]:
        manual_status = self._mapping(
            controller_status.get(
                "manual_command"
            )
        )

        if not manual_status:
            manual_status = self._mapping(
                controller_status.get(
                    "manual"
                )
            )

        active_command = (
            manual_status.get("active")
            or manual_status.get(
                "active_command"
            )
        )

        if active_command:
            status = "WARNING"
            message = (
                "Une commande manuelle est active ou en attente."
            )
        else:
            status = "PASS"
            message = (
                "Aucune commande manuelle active détectée."
            )

        return self._check(
            key="manual_command_pipeline",
            label="Pipeline des commandes manuelles",
            status=status,
            required=True,
            message=message,
            details={
                "active_command": active_command,
                "status": manual_status,
            },
        )

    @staticmethod
    def _recommendations(
        *,
        simulation: bool,
        failed: list[dict[str, Any]],
        warnings: list[dict[str, Any]],
        controller_status: dict[str, Any],
    ) -> list[str]:
        recommendations: list[str] = []

        if failed:
            recommendations.append(
                "Corriger tous les contrôles en échec avant "
                "d'autoriser un test physique."
            )

        if simulation:
            recommendations.append(
                "Basculer vers le Driver MQTT réel uniquement "
                "après raccordement et contrôle des sorties."
            )

        warning_keys = {
            item.get("key")
            for item in warnings
        }

        if "mqtt_driver" in warning_keys:
            recommendations.append(
                "Vérifier la connexion au broker MQTT et "
                "la réception du heartbeat ESP32."
            )

        if "esp32" in warning_keys:
            recommendations.append(
                "Vérifier l'alimentation, l'Ethernet, le firmware "
                "et le heartbeat du WT32-ETH01."
            )

        if "thermal_sensors" in warning_keys:
            recommendations.append(
                "Contrôler les identifiants et l'emplacement "
                "des sondes avant les essais hydrauliques."
            )

        if "actuator_observation" in warning_keys:
            recommendations.append(
                "Mettre physiquement pompe et vanne à l'arrêt "
                "avant de poursuivre le raccordement."
            )

        mode = str(
            controller_status.get(
                "mode",
                "UNKNOWN",
            )
        ).upper()

        if mode not in {
            "OFF",
            "SIMULATION",
            "MANUAL_SAFE",
            "MANUAL",
        }:
            recommendations.append(
                "Placer le contrôleur en OFF ou MANUAL_SAFE "
                "pour la mise en service."
            )

        if not recommendations:
            recommendations.append(
                "La couche logicielle est prête pour la prochaine "
                "étape de mise en service contrôlée."
            )

        return recommendations

    def status(self) -> dict[str, Any]:
        """Retourne la checklist de mise en service."""

        controller_status, controller_error = (
            self._safe_controller_status()
        )

        health_status, health_error = (
            self._safe_health_status()
        )

        components = self._mapping(
            health_status.get("components")
        )

        simulation = bool(
            health_status.get(
                "simulation",
                controller_status.get(
                    "simulation",
                    False,
                ),
            )
        )

        checks = [
            self._build_database_check(
                components
            ),
            self._build_controller_check(
                components
            ),
            self._build_brain_check(
                components
            ),
            self._build_driver_check(
                components,
                simulation,
            ),
            self._build_esp_check(
                components,
                simulation,
            ),
            self._build_thermal_check(
                components,
                simulation,
            ),
            self._build_safety_check(
                components
            ),
            self._build_actuator_observation(
                components,
                simulation,
            ),
            self._build_manual_pipeline_check(
                controller_status
            ),
        ]

        if controller_error:
            checks.append(
                self._check(
                    key="controller_status_read",
                    label="Lecture du Controller",
                    status="FAIL",
                    required=True,
                    message=(
                        "Impossible de lire le Controller."
                    ),
                    details={
                        "error": controller_error,
                    },
                )
            )

        if health_error:
            checks.append(
                self._check(
                    key="health_status_read",
                    label="Lecture du Health Manager",
                    status="FAIL",
                    required=True,
                    message=(
                        "Impossible de lire le Health Manager."
                    ),
                    details={
                        "error": health_error,
                    },
                )
            )

        failed = [
            item
            for item in checks
            if item["status"] == "FAIL"
        ]

        warnings = [
            item
            for item in checks
            if item["status"] == "WARNING"
        ]

        passed = [
            item
            for item in checks
            if item["status"] == "PASS"
        ]

        required_failures = [
            item
            for item in failed
            if item["required"]
        ]

        required_warnings = [
            item
            for item in warnings
            if item["required"]
        ]

        technically_ready = (
            not required_failures
            and not required_warnings
        )

        ready_for_real_hardware = (
            technically_ready
            and not simulation
        )

        if required_failures:
            overall = "BLOCKED"
            phase = "FAULT_DIAGNOSIS"

        elif required_warnings:
            overall = "ATTENTION"
            phase = (
                "SIMULATION_VALIDATED"
                if simulation
                else "COMMISSIONING_REQUIRED"
            )

        else:
            overall = "READY"
            phase = (
                "SOFTWARE_READY"
                if simulation
                else "READY_FOR_CONTROLLED_TEST"
            )

        recommendations = self._recommendations(
            simulation=simulation,
            failed=failed,
            warnings=warnings,
            controller_status=controller_status,
        )

        return {
            "component": "geocooling",
            "view": "commissioning",
            "generated_at": utc_now_iso(),
            "read_only": True,
            "overall": overall,
            "phase": phase,
            "simulation": simulation,
            "technically_ready": technically_ready,
            "ready_for_real_hardware": (
                ready_for_real_hardware
            ),
            "summary": {
                "total": len(checks),
                "passed": len(passed),
                "warnings": len(warnings),
                "failed": len(failed),
            },
            "checklist": checks,
            "blockers": [
                {
                    "key": item["key"],
                    "label": item["label"],
                    "message": item["message"],
                }
                for item in required_failures
            ],
            "attention": [
                {
                    "key": item["key"],
                    "label": item["label"],
                    "message": item["message"],
                }
                for item in required_warnings
            ],
            "recommendations": recommendations,
            "observations": {
                "controller_state": (
                    controller_status.get("state")
                ),
                "controller_mode": (
                    controller_status.get("mode")
                ),
                "health_overall": (
                    health_status.get("overall")
                ),
                "health_generated_at": (
                    health_status.get(
                        "generated_at"
                    )
                ),
            },
        }
