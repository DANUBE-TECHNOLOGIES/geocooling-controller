from __future__ import annotations

from app.geocooling.hardware_readiness import GeoCoolingHardwareReadiness


class FakeGateway:
    def __init__(self) -> None:
        self.commands: list[str] = []

    def status(self):
        return {
            "gateway_mode": "simulation", "armed": False, "valve_open": False,
            "pump_running": False, "device": {"host": "192.168.10.200", "port": 502,
            "unit_id": 1, "valve_relay": 1, "pump_relay": 2},
        }

    def dry_run(self, command: str):
        self.commands.append(command)
        return {"command": command, "accepted": True, "dry_run": True, "hardware_touched": False}


class FakeSafety:
    def status(self):
        return {"emergency_stop": False}


class FakeJournal:
    def __init__(self):
        self.events = []

    def record(self, component, event, **kwargs):
        self.events.append((component, event, kwargs))


def test_readiness_is_safe_and_non_activating(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "false")
    service = GeoCoolingHardwareReadiness(FakeGateway(), FakeSafety(), FakeJournal())
    result = service.status()
    assert result["status"] == "PASS"
    assert result["gateway_mode"] == "simulation"
    assert result["activation_preconditions_met"] is False
    assert result["activation_allowed"] is False
    assert result["hardware_touched"] is False


def test_dry_run_uses_safe_order_and_never_touches_hardware(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "false")
    gateway = FakeGateway()
    service = GeoCoolingHardwareReadiness(gateway, FakeSafety(), FakeJournal())
    result = service.dry_run_sequence()
    assert gateway.commands == ["SAFE_STATE", "OPEN_VALVE", "START_PUMP", "STOP_PUMP", "CLOSE_VALVE", "SAFE_STATE"]
    assert result["status"] == "PASS"
    assert result["activation_allowed"] is False
    assert result["hardware_touched"] is False


def test_invalid_mapping_fails(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "false")
    gateway = FakeGateway()
    data = gateway.status()
    data["device"]["pump_relay"] = 1
    gateway.status = lambda: data
    result = GeoCoolingHardwareReadiness(gateway, FakeSafety(), FakeJournal()).status()
    assert result["status"] == "FAIL"
    assert result["activation_preconditions_met"] is False


def test_armed_environment_fails(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "true")
    result = GeoCoolingHardwareReadiness(FakeGateway(), FakeSafety(), FakeJournal()).status()
    assert result["status"] == "FAIL"
