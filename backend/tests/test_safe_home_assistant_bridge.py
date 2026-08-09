from __future__ import annotations

from app.geocooling.brain_v2.integration.home_assistant_bridge import (
    HomeAssistantBridge,
)
from app.geocooling.brain_v2.integration.safe_home_assistant_bridge import (
    SafeHomeAssistantBridge,
)


def test_state_marks_missing_hydraulic_roles(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        HomeAssistantBridge,
        "state",
        lambda self: {
            "version": "legacy",
            "floor_surface_temperature_c": 22.0,
            "floor_supply_temperature_c": None,
            "floor_return_temperature_c": 20.1,
        },
    )
    monkeypatch.setattr(
        SafeHomeAssistantBridge,
        "_latest_snapshot",
        lambda self: {
            "source_inlet_temperature_c": 12.3,
            "source_outlet_temperature_c": None,
            "flow_rate_l_min": 28.0,
        },
    )

    bridge = SafeHomeAssistantBridge(data_directory=tmp_path)
    state = bridge.state()

    assert state["telemetry_complete"] is False
    assert state["fail_safe_missing_values"] is True
    assert state["hydraulic_role_count"] == 6
    assert state["hydraulic_roles_ready"] == 4
    assert state["missing_measurements"] == [
        "floor_supply_temperature_c",
        "source_outlet_temperature_c",
    ]
    assert state["source_inlet_temperature_c"] == 12.3
    assert state["flow_rate_l_min"] == 28.0
    assert state["version"] == SafeHomeAssistantBridge.VERSION


def test_package_never_coerces_missing_values_to_zero(monkeypatch, tmp_path) -> None:
    monkeypatch.setattr(
        HomeAssistantBridge,
        "package_yaml",
        lambda self, base_url: """rest:\n  sensor:\n    state_a: '{{ value | float(0) }}'\n    state_b: '{{ value | int(0) }}'\n          - floor_return_temperature_c\n          - relay_command\n      - name: GeoCooling cible Brain\n""",
    )

    bridge = SafeHomeAssistantBridge(data_directory=tmp_path)
    package = bridge.package_yaml("http://controller:8000")

    assert "float(0)" not in package
    assert "int(0)" not in package
    assert "float(none)" in package
    assert "int(none)" in package
    assert "source_inlet_temperature_c" in package
    assert "source_outlet_temperature_c" in package
    assert "flow_rate_l_min" in package
    assert "GeoCooling débit hydraulique" in package
    assert "telemetry_complete" in package
    assert "missing_measurements" in package
    assert package.startswith("# FAIL-SAFE:")
