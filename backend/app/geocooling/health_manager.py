"""Diagnostic consolidé du sous-système GeoCooling.

Ce module est strictement en lecture seule.

Il ne doit jamais :

- piloter la pompe ;
- piloter la vanne ;
- changer le mode du contrôleur ;
- modifier l'état du contrôleur ;
- exécuter une commande manuelle ;
- prendre une décision à la place du Brain.
"""

from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

from sqlalchemy import text


def utc_now() -> datetime:
    """Retourne la date courante en UTC."""

    return datetime.now(timezone.utc)


def parse_datetime(value: Any) -> datetime | None:
    """Convertit une valeur en datetime UTC lorsque cela est possible."""

    if isinstance(value, datetime):
        parsed = value

    elif isinstance(value, str) and value.strip():
        try:
            parsed = datetime.fromisoformat(
                value.strip().replace("Z", "+00:00")
            )
        except ValueError:
            return None

    else:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)

    return parsed.astimezone(timezone.utc)


def age_seconds(value: Any) -> float | None:
    """Retourne l'âge en secondes d'un horodatage."""

    parsed = parse_datetime(value)

    if parsed is None:
        return None

    return max(
        0.0,
        round(
            (utc_now() - parsed).total_seconds(),
            3,
        ),
    )


class GeoCoolingHealthManager:
    """Construit un diagnostic GeoCooling sans effet physique."""

    def __init__(self, controller: Any) -> None:
        self.controller = controller

        self.sensor_stale_seconds = max(
            10,
            int(
                os.getenv(
                    "GEOCOOLING_SENSOR_STALE_SECONDS",
                    "90",
                )
            ),
        )

        self.heartbeat_timeout_seconds = max(
            10,
            int(
                os.getenv(
                    "GEOCOOLING_HEARTBEAT_TIMEOUT_SECONDS",
                    "90",
                )
            ),
        )

    @staticmethod
    def _component(
        *,
        status: str,
        message: str,
        **details: Any,
    ) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "status": status,
            "message": message,
        }

        payload.update(details)

        return payload

    @staticmethod
    def _mapping(value: Any) -> dict[str, Any]:
        if isinstance(value, dict):
            return value

        return {}

    def _database_health(self) -> dict[str, Any]:
        """Teste PostgreSQL avec une requête SELECT 1."""

        engine = getattr(self.controller, "engine", None)

        if engine is None:
            return self._component(
                status="ERROR",
                message="Moteur PostgreSQL indisponible.",
            )

        try:
            with engine.connect() as connection:
                value = connection.execute(
                    text("SELECT 1")
                ).scalar_one()

            if value != 1:
                raise RuntimeError(
                    f"Réponse PostgreSQL inattendue : {value!r}"
                )

            return self._component(
                status="OK",
                message="PostgreSQL accessible.",
            )

        except Exception as exc:
            return self._component(
                status="ERROR",
                message="PostgreSQL inaccessible.",
                error=str(exc),
            )

    def _controller_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        state = str(
            status.get(
                "state",
                "UNKNOWN",
            )
        ).upper()

        last_error = status.get("last_error")

        if state in {
            "FAULT",
            "ERROR",
            "EMERGENCY_STOP",
        }:
            level = "ERROR"
            message = "Le contrôleur est en défaut."

        elif last_error:
            level = "WARNING"
            message = "Le contrôleur signale une erreur récente."

        else:
            level = "OK"
            message = "Contrôleur opérationnel."

        return self._component(
            status=level,
            message=message,
            state=state,
            mode=status.get("mode"),
            simulation=bool(
                status.get(
                    "simulation",
                    False,
                )
            ),
            last_event=status.get("last_event"),
            last_reason=status.get("last_reason"),
            last_error=last_error,
            state_changed_at=status.get(
                "state_changed_at"
            ),
            runtime_seconds=status.get(
                "runtime_seconds",
                0,
            ),
        )

    def _driver_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        driver = self._mapping(
            status.get("driver")
        )

        simulation = bool(
            driver.get(
                "simulation",
                status.get(
                    "simulation",
                    False,
                ),
            )
        )

        connected = bool(
            driver.get(
                "connected",
                simulation,
            )
        )

        device_online = bool(
            driver.get(
                "device_online",
                driver.get(
                    "online",
                    simulation,
                ),
            )
        )

        last_message_at = driver.get(
            "last_message_at"
        )

        last_heartbeat_at = driver.get(
            "last_heartbeat_at"
        )

        last_message_age = age_seconds(
            last_message_at
        )

        heartbeat_age = age_seconds(
            last_heartbeat_at
        )

        if simulation:
            level = "OK"
            message = "Pilote de simulation opérationnel."

        elif not connected:
            level = "ERROR"
            message = "Pilote MQTT déconnecté."

        elif not device_online:
            level = "ERROR"
            message = "ESP32 hors ligne."

        elif (
            heartbeat_age is not None
            and heartbeat_age
            > self.heartbeat_timeout_seconds
        ):
            level = "ERROR"
            message = "Heartbeat ESP32 expiré."

        else:
            level = "OK"
            message = "Pilote MQTT connecté."

        return self._component(
            status=level,
            message=message,
            name=status.get(
                "driver_name",
                driver.get("driver"),
            ),
            simulation=simulation,
            connected=connected,
            device_online=device_online,
            valve_open=bool(
                driver.get(
                    "valve_open",
                    False,
                )
            ),
            pump_running=bool(
                driver.get(
                    "pump_running",
                    False,
                )
            ),
            last_message_at=last_message_at,
            last_message_age_seconds=last_message_age,
            last_heartbeat_at=last_heartbeat_at,
            heartbeat_age_seconds=heartbeat_age,
            heartbeat_timeout_seconds=(
                self.heartbeat_timeout_seconds
            ),
            last_action_at=driver.get(
                "last_action_at"
            ),
            last_error=driver.get("last_error"),
        )

    def _device_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        device = self._mapping(
            status.get("device")
        )

        simulation = bool(
            device.get(
                "simulation",
                status.get(
                    "simulation",
                    False,
                ),
            )
        )

        connected = bool(
            device.get(
                "connected",
                simulation,
            )
        )

        online = bool(
            device.get(
                "online",
                simulation,
            )
        )

        heartbeat_fresh = bool(
            device.get(
                "heartbeat_fresh",
                simulation,
            )
        )

        ready = bool(
            device.get(
                "ready",
                simulation
                or (
                    connected
                    and online
                    and heartbeat_fresh
                ),
            )
        )

        if simulation:
            level = "OK"
            message = "Matériel simulé."

        elif ready and connected and online and heartbeat_fresh:
            level = "OK"
            message = "ESP32 opérationnel."

        elif not connected or not online:
            level = "ERROR"
            message = "ESP32 indisponible."

        else:
            level = "WARNING"
            message = "ESP32 connecté mais non prêt."

        reason = device.get("reason")

        if reason:
            message = str(reason)

        return self._component(
            status=level,
            message=message,
            ready=ready,
            simulation=simulation,
            connected=connected,
            online=online,
            heartbeat_fresh=heartbeat_fresh,
        )

    def _brain_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        brain = self._mapping(
            status.get("brain")
        )

        decision = brain.get("decision")
        generated_at = brain.get("generated_at")
        generated_age = age_seconds(generated_at)

        if not brain:
            level = "ERROR"
            message = "Aucun état Brain disponible."

        elif not decision:
            level = "WARNING"
            message = "Décision Brain absente."

        else:
            operating_mode = str(
                brain.get("operating_mode") or ""
            ).upper()

            if operating_mode == "INSUFFICIENT_DATA":
                level = "WARNING"
                message = (
                    "Brain disponible mais données bâtiment insuffisantes."
                )
            elif operating_mode == "LIMITED":
                level = "WARNING"
                message = (
                    "Brain opérationnel avec mesures bâtiment partielles."
                )
            elif operating_mode == "BUILDING_ONLY":
                level = "OK"
                message = (
                    "Brain opérationnel en mode bâtiment uniquement."
                )
            else:
                level = "OK"
                message = "Brain opérationnel."

        return self._component(
            status=level,
            message=message,
            decision=decision,
            confidence=brain.get("confidence"),
            data_quality=brain.get("data_quality"),
            operating_mode=brain.get(
                "operating_mode"
            ),
            generated_at=generated_at,
            age_seconds=generated_age,
            reason=brain.get("reason"),
        )

    def _thermal_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        thermal = self._mapping(
            status.get("thermal")
        )

        latest = self._mapping(
            thermal.get("latest")
        )

        timestamp = latest.get("timestamp")
        measurement_age = age_seconds(timestamp)

        monitored_fields = (
            "indoor_temperature_c",
            "indoor_humidity_percent",
            "surface_temperature_c",
            "floor_supply_temperature_c",
            "floor_return_temperature_c",
            "source_inlet_temperature_c",
            "source_outlet_temperature_c",
            "outdoor_temperature_c",
            "flow_rate_l_min",
        )

        values = {
            field: latest.get(field)
            for field in monitored_fields
        }

        detected = [
            field
            for field, value in values.items()
            if value is not None
        ]

        missing = [
            field
            for field, value in values.items()
            if value is None
        ]

        invalid: list[str] = []

        temperature_fields = (
            "indoor_temperature_c",
            "surface_temperature_c",
            "floor_supply_temperature_c",
            "floor_return_temperature_c",
            "source_inlet_temperature_c",
            "source_outlet_temperature_c",
            "outdoor_temperature_c",
        )

        for field in temperature_fields:
            value = values.get(field)

            if value is None:
                continue

            try:
                numeric = float(value)
            except (TypeError, ValueError):
                invalid.append(field)
                continue

            if numeric < -30.0 or numeric > 90.0:
                invalid.append(field)

        humidity = values.get(
            "indoor_humidity_percent"
        )

        if humidity is not None:
            try:
                humidity_value = float(humidity)
            except (TypeError, ValueError):
                invalid.append(
                    "indoor_humidity_percent"
                )
            else:
                if (
                    humidity_value < 0.0
                    or humidity_value > 100.0
                ):
                    invalid.append(
                        "indoor_humidity_percent"
                    )

        flow_rate = values.get(
            "flow_rate_l_min"
        )

        if flow_rate is not None:
            try:
                flow_value = float(flow_rate)
            except (TypeError, ValueError):
                invalid.append(
                    "flow_rate_l_min"
                )
            else:
                if flow_value < 0.0:
                    invalid.append(
                        "flow_rate_l_min"
                    )

        available = bool(
            thermal.get(
                "available",
                bool(latest),
            )
        )

        stale = (
            measurement_age is None
            or measurement_age
            > self.sensor_stale_seconds
        )

        if invalid:
            level = "ERROR"
            message = "Mesures thermiques invalides."

        elif not available:
            level = "WARNING"
            message = "Mesures thermiques indisponibles."

        elif stale:
            level = "WARNING"
            message = "Mesures thermiques trop anciennes."

        else:
            level = "OK"
            message = "Mesures thermiques disponibles."

        return self._component(
            status=level,
            message=message,
            available=available,
            timestamp=timestamp,
            age_seconds=measurement_age,
            stale=stale,
            stale_after_seconds=(
                self.sensor_stale_seconds
            ),
            detected_count=len(detected),
            detected=detected,
            missing=missing,
            invalid=sorted(set(invalid)),
            values=values,
            history_count=thermal.get(
                "history_count",
                0,
            ),
        )

    def _safety_health(
        self,
        status: dict[str, Any],
    ) -> dict[str, Any]:
        safety = self._mapping(
            status.get("safety")
        )

        safe = bool(
            safety.get(
                "safe",
                False,
            )
        )

        safety_level = str(
            safety.get(
                "level",
                "unknown",
            )
        ).lower()

        if not safety:
            level = "WARNING"
            message = "État Safety indisponible."

        elif not safe:
            level = "ERROR"
            message = str(
                safety.get(
                    "reason",
                    "Condition de sécurité non satisfaite.",
                )
            )

        elif safety_level in {
            "unavailable",
            "degraded",
            "warning",
        }:
            level = "WARNING"
            message = str(
                safety.get(
                    "reason",
                    "Sécurité en mode dégradé.",
                )
            )

        else:
            level = "OK"
            message = str(
                safety.get(
                    "reason",
                    "Conditions de sécurité satisfaites.",
                )
            )

        return self._component(
            status=level,
            message=message,
            safe=safe,
            level=safety_level,
            dew_point_c=safety.get(
                "dew_point_c"
            ),
            surface_temperature_c=safety.get(
                "surface_temperature_c"
            ),
            margin_c=safety.get("margin_c"),
        )

    def status(self) -> dict[str, Any]:
        """Retourne le diagnostic consolidé GeoCooling."""

        generated_at = utc_now()

        try:
            controller_status = self.controller.status()

            if not isinstance(
                controller_status,
                dict,
            ):
                raise TypeError(
                    "controller.status() n'a pas retourné un dictionnaire."
                )

            status_error = None

        except Exception as exc:
            controller_status = {}
            status_error = str(exc)

        if controller_status:
            controller_component = (
                self._controller_health(
                    controller_status
                )
            )

            driver_component = (
                self._driver_health(
                    controller_status
                )
            )

            device_component = (
                self._device_health(
                    controller_status
                )
            )

            brain_component = (
                self._brain_health(
                    controller_status
                )
            )

            thermal_component = (
                self._thermal_health(
                    controller_status
                )
            )

            safety_component = (
                self._safety_health(
                    controller_status
                )
            )

        else:
            controller_component = self._component(
                status="ERROR",
                message=(
                    "Impossible de lire l'état "
                    "du contrôleur."
                ),
                error=status_error,
            )

            driver_component = self._component(
                status="ERROR",
                message="État Driver indisponible.",
            )

            device_component = self._component(
                status="ERROR",
                message="État ESP32 indisponible.",
            )

            brain_component = self._component(
                status="ERROR",
                message="État Brain indisponible.",
            )

            thermal_component = self._component(
                status="WARNING",
                message="État thermique indisponible.",
            )

            safety_component = self._component(
                status="WARNING",
                message="État Safety indisponible.",
            )

        components = {
            "database": self._database_health(),
            "controller": controller_component,
            "driver": driver_component,
            "device": device_component,
            "brain": brain_component,
            "thermal": thermal_component,
            "safety": safety_component,
        }

        errors: list[str] = []
        warnings: list[str] = []

        for name, component in components.items():
            component_level = component.get(
                "status",
                "ERROR",
            )

            component_message = component.get(
                "message",
                "État inconnu.",
            )

            if component_level == "ERROR":
                errors.append(
                    f"{name}: {component_message}"
                )

            elif component_level == "WARNING":
                warnings.append(
                    f"{name}: {component_message}"
                )

        if errors:
            overall = "ERROR"
            technically_ready = False

        elif warnings:
            overall = "WARNING"
            technically_ready = False

        else:
            overall = "GOOD"
            technically_ready = True

        simulation = bool(
            controller_status.get(
                "simulation",
                False,
            )
        )

        return {
            "component": "geocooling",
            "overall": overall,
            "generated_at": generated_at.isoformat(),
            "read_only": True,
            "simulation": simulation,
            "technically_ready": technically_ready,
            "ready_for_real_hardware": (
                technically_ready
                and not simulation
            ),
            "components": components,
            "warnings": warnings,
            "errors": errors,
        }
