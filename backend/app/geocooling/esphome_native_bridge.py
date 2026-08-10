"""Read-only ESPHome Native API -> GeoCooling telemetry bridge.

This process subscribes to sensor states from the WT32/ESPHome controller and
normalizes only the confirmed hydraulic temperature entities into the existing
``sensor_measurements`` table. It exposes no ESPHome command path and never
controls EV, M11, M13 or the Waveshare relay board.
"""

from __future__ import annotations

import asyncio
import logging
import math
import os
from dataclasses import dataclass
from typing import Any

import aioesphomeapi
from sqlalchemy import create_engine, text

LOGGER = logging.getLogger("geocooling.esphome_bridge")

DEFAULT_ENTITY_MAPPING: dict[str, str] = {
    "GeoCooling - Arrivée Forage": "gc_source_inlet",
    "GeoCooling - Retour Forage": "gc_source_outlet",
    "GeoCooling - Départ Plancher": "gc_floor_supply",
    "GeoCooling - Retour Plancher": "gc_floor_return",
}

INSERT_MEASUREMENT_SQL = text(
    """
    INSERT INTO sensor_measurements (
        source,
        sensor_name,
        metric,
        value,
        unit,
        quality,
        mqtt_topic
    )
    VALUES (
        'esphome_native_api',
        :sensor_name,
        'temperature',
        :value,
        '°C',
        'good',
        :source_uri
    )
    """
)


@dataclass(frozen=True)
class BridgeConfig:
    host: str
    port: int
    noise_psk: str
    database_url: str
    reconnect_seconds: float

    @classmethod
    def from_environment(cls) -> "BridgeConfig":
        return cls(
            host=os.getenv("ESPHOME_BRIDGE_HOST", "192.168.10.105").strip(),
            port=int(os.getenv("ESPHOME_BRIDGE_PORT", "6053")),
            noise_psk=os.getenv("ESPHOME_BRIDGE_NOISE_PSK", "").strip(),
            database_url=os.environ["DATABASE_URL"],
            reconnect_seconds=max(
                1.0,
                float(os.getenv("ESPHOME_BRIDGE_RECONNECT_SECONDS", "5")),
            ),
        )


def build_entity_key_mapping(
    entities: list[Any],
    entity_mapping: dict[str, str] | None = None,
) -> dict[int, str]:
    """Map ESPHome entity keys to canonical GeoCooling sensor names."""
    expected = entity_mapping or DEFAULT_ENTITY_MAPPING
    result: dict[int, str] = {}

    for entity in entities:
        name = str(getattr(entity, "name", "") or "")
        key = getattr(entity, "key", None)
        canonical_name = expected.get(name)

        if canonical_name is None or key is None:
            continue

        result[int(key)] = canonical_name

    return result


def normalize_sensor_state(
    state: Any,
    entity_keys: dict[int, str],
    *,
    host: str,
) -> dict[str, Any] | None:
    """Normalize one ESPHome SensorState without allowing any commands."""
    key = getattr(state, "key", None)
    value = getattr(state, "state", None)

    if key is None or int(key) not in entity_keys:
        return None

    if not isinstance(value, (int, float)) or isinstance(value, bool):
        return None

    numeric_value = float(value)
    if not math.isfinite(numeric_value):
        return None

    sensor_name = entity_keys[int(key)]
    return {
        "sensor_name": sensor_name,
        "value": numeric_value,
        "source_uri": f"esphome-native://{host}/{sensor_name}",
    }


class ESPHomeNativeTelemetryBridge:
    """Subscribe to ESPHome states and persist only approved measurements."""

    def __init__(self, config: BridgeConfig) -> None:
        self.config = config
        self.engine = create_engine(config.database_url, pool_pre_ping=True)
        self.entity_keys: dict[int, str] = {}
        self.connected = False
        self.last_error: str | None = None
        self.measurement_count = 0

    def persist(self, measurement: dict[str, Any]) -> None:
        with self.engine.begin() as connection:
            connection.execute(INSERT_MEASUREMENT_SQL, measurement)
        self.measurement_count += 1

    async def run_session(self) -> None:
        if not self.config.noise_psk:
            raise RuntimeError(
                "ESPHOME_BRIDGE_NOISE_PSK est requis pour l'API ESPHome chiffrée."
            )

        stopped = asyncio.Event()

        async def on_stop(expected_disconnect: bool) -> None:
            del expected_disconnect
            self.connected = False
            stopped.set()

        api = aioesphomeapi.APIClient(
            self.config.host,
            self.config.port,
            noise_psk=self.config.noise_psk,
        )

        try:
            await api.connect(on_stop=on_stop, login=True)
            entities, _services = await api.list_entities_services()
            self.entity_keys = build_entity_key_mapping(entities)

            missing = sorted(
                set(DEFAULT_ENTITY_MAPPING.values()) - set(self.entity_keys.values())
            )
            if missing:
                raise RuntimeError(
                    "Entités ESPHome GeoCooling manquantes: " + ", ".join(missing)
                )

            def on_state(state: Any) -> None:
                measurement = normalize_sensor_state(
                    state,
                    self.entity_keys,
                    host=self.config.host,
                )
                if measurement is None:
                    return

                try:
                    self.persist(measurement)
                    self.last_error = None
                except Exception as exc:  # pragma: no cover - runtime DB failure
                    self.last_error = str(exc)
                    LOGGER.exception("Impossible d'historiser la mesure ESPHome")

            api.subscribe_states(on_state)
            self.connected = True
            self.last_error = None
            LOGGER.info(
                "Bridge ESPHome connecté à %s:%s (%s sondes hydrauliques)",
                self.config.host,
                self.config.port,
                len(self.entity_keys),
            )
            await stopped.wait()
        finally:
            self.connected = False
            await api.disconnect(force=True)

    async def run_forever(self) -> None:
        while True:
            try:
                await self.run_session()
            except asyncio.CancelledError:
                raise
            except Exception as exc:
                self.connected = False
                self.last_error = str(exc)
                LOGGER.warning("Bridge ESPHome indisponible: %s", exc)

            await asyncio.sleep(self.config.reconnect_seconds)


def main() -> None:
    logging.basicConfig(
        level=getattr(
            logging,
            os.getenv("LOG_LEVEL", "INFO").upper(),
            logging.INFO,
        ),
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    bridge = ESPHomeNativeTelemetryBridge(BridgeConfig.from_environment())
    asyncio.run(bridge.run_forever())


if __name__ == "__main__":
    main()
