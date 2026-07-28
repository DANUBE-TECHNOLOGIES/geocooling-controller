import os
from datetime import datetime, timezone
from typing import Any


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def parse_datetime(
    value: str | None,
) -> datetime | None:
    if not value:
        return None

    try:
        parsed = datetime.fromisoformat(value)
    except ValueError:
        return None

    if parsed.tzinfo is None:
        parsed = parsed.replace(
            tzinfo=timezone.utc,
        )

    return parsed.astimezone(timezone.utc)


class DeviceManager:
    """
    Évalue la disponibilité du matériel GeoCooling.

    Ce composant ne commande aucun relais.
    Il transforme les informations du pilote en état exploitable
    par le contrôleur et, au sprint suivant, par le Safety Manager.
    """

    def __init__(self, driver: Any) -> None:
        self.driver = driver

        self.heartbeat_timeout_seconds = max(
            10,
            int(
                os.getenv(
                    "GEOCOOLING_HEARTBEAT_TIMEOUT_SECONDS",
                    "90",
                )
            ),
        )

    def status(self) -> dict[str, Any]:
        driver_status = self.driver.status()

        simulation = bool(
            driver_status.get(
                "simulation",
                False,
            )
        )

        if simulation:
            return {
                "ready": True,
                "simulation": True,
                "connected": True,
                "online": True,
                "heartbeat_fresh": True,
                "reason": (
                    "Matériel simulé : aucune présence ESP32 "
                    "requise."
                ),
                "driver": driver_status,
            }

        connected = bool(
            driver_status.get(
                "connected",
                False,
            )
        )

        if driver_status.get("driver") == "waveshare_modbus":
            armed = bool(driver_status.get("armed", False))
            ready = connected and armed
            return {
                "ready": ready,
                "simulation": False,
                "connected": connected,
                "online": connected,
                "heartbeat_fresh": connected,
                "reason": (
                    "Waveshare Modbus disponible et armé"
                    if ready
                    else (
                        "Waveshare Modbus disponible mais désarmé"
                        if connected
                        else "Waveshare Modbus inaccessible"
                    )
                ),
                "driver": driver_status,
            }

        online = bool(
            driver_status.get(
                "device_online",
                False,
            )
        )

        heartbeat_at = parse_datetime(
            driver_status.get(
                "last_heartbeat_at"
            )
        )

        heartbeat_age_seconds: int | None = None
        heartbeat_fresh = False

        if heartbeat_at is not None:
            heartbeat_age_seconds = max(
                0,
                int(
                    (
                        utc_now()
                        - heartbeat_at
                    ).total_seconds()
                ),
            )

            heartbeat_fresh = (
                heartbeat_age_seconds
                <= self.heartbeat_timeout_seconds
            )

        ready = (
            connected
            and online
            and heartbeat_fresh
        )

        reasons: list[str] = []

        if not connected:
            reasons.append(
                "pilote MQTT déconnecté"
            )

        if not online:
            reasons.append(
                "ESP32 non disponible"
            )

        if not heartbeat_fresh:
            reasons.append(
                "heartbeat absent ou trop ancien"
            )

        return {
            "ready": ready,
            "simulation": False,
            "connected": connected,
            "online": online,
            "heartbeat_fresh": heartbeat_fresh,
            "heartbeat_age_seconds":
                heartbeat_age_seconds,
            "heartbeat_timeout_seconds":
                self.heartbeat_timeout_seconds,
            "reason": (
                "Matériel GeoCooling disponible"
                if ready
                else ", ".join(reasons)
            ),
            "driver": driver_status,
        }
