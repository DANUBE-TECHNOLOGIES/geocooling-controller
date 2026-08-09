from __future__ import annotations

from app.geocooling.brain_v2.integration.home_assistant_bridge import (
    HomeAssistantBridge,
)
from app.geocooling.brain_v2.integration.safe_home_assistant_bridge import (
    SafeHomeAssistantBridge,
)


def test_state_marks_missing_critical_measurements(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        HomeAssistantBridge,
        "state",
        lambda self: {
            "version": "legacy",
            "indoor_temperature_c": 24.2,
            "indoor_humidity_percent": 52.0,
            "floor_surface_temperature_c": None,
            "floor_supply_temperature_c": None,
            "floor_return_temperature_c": 20.1,
        },
    )

    bridge = SafeHomeAssistantBridge(data_directory=tmp_path)
    state = bridge.state()

    assert state["telemetry_complete"] is False
    assert state["fail_safe_missing_values"] is True
    assert state["missing_measurements"] == [
        "floor_surface_temperature_c",
        "floor_supply_temperature_c",
    ]
    assert state["version"] == SafeHomeAssistantBridge.VERSION


def test_package_never_coerces_missing_values_to_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        HomeAssistantBridge,
        "package_yaml",
        lambda self, base_url: """rest:\n  sensor:\n    state_a: '{{ value | float(0) }}'\n    state_b: '{{ value | int(0) }}'\n          - relay_command\n""",
    )

    bridge = SafeHomeAssistantBridge(data_directory=tmp_path)
    package = bridge.package_yaml("http://controller:8000")

    assert "float(0)" not in package
    assert "int(0)" not in package
    assert "float(none)" in package
    assert "int(none)" in package
    assert "telemetry_complete" in package
    assert "missing_measurements" in package
    assert package.startswith("# FAIL-SAFE:")
