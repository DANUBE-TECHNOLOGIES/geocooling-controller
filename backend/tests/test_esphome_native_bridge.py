from types import SimpleNamespace

from app.geocooling.esphome_native_bridge import (
    DEFAULT_ENTITY_MAPPING,
    build_entity_key_mapping,
    normalize_sensor_state,
)


def test_build_entity_key_mapping_accepts_only_confirmed_hydraulic_entities():
    entities = [
        SimpleNamespace(key=1, name="GeoCooling - Arrivée Forage"),
        SimpleNamespace(key=2, name="GeoCooling - Retour Forage"),
        SimpleNamespace(key=3, name="GeoCooling - Départ Plancher"),
        SimpleNamespace(key=4, name="GeoCooling - Retour Plancher"),
        SimpleNamespace(key=5, name="GeoCooling - Température Plancher"),
        SimpleNamespace(key=6, name="Température interne ESP32"),
    ]

    mapping = build_entity_key_mapping(entities)

    assert mapping == {
        1: "gc_source_inlet",
        2: "gc_source_outlet",
        3: "gc_floor_supply",
        4: "gc_floor_return",
    }
    assert set(mapping.values()) == set(DEFAULT_ENTITY_MAPPING.values())


def test_normalize_sensor_state_builds_canonical_temperature_measurement():
    state = SimpleNamespace(key=3, state=24.5625)

    measurement = normalize_sensor_state(
        state,
        {3: "gc_floor_supply"},
        host="192.168.10.105",
    )

    assert measurement == {
        "sensor_name": "gc_floor_supply",
        "value": 24.5625,
        "source_uri": "esphome-native://192.168.10.105/gc_floor_supply",
    }


def test_normalize_sensor_state_ignores_unapproved_and_invalid_values():
    assert normalize_sensor_state(
        SimpleNamespace(key=99, state=20.0),
        {1: "gc_source_inlet"},
        host="192.168.10.105",
    ) is None

    assert normalize_sensor_state(
        SimpleNamespace(key=1, state=float("nan")),
        {1: "gc_source_inlet"},
        host="192.168.10.105",
    ) is None

    assert normalize_sensor_state(
        SimpleNamespace(key=1, state=True),
        {1: "gc_source_inlet"},
        host="192.168.10.105",
    ) is None
