import pytest

from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver


class FakeClient:
    def __init__(self):
        self.coils = {}
        self.writes = []

    def read_coil(self, address):
        return bool(self.coils.get(address, False))

    def write_coil(self, address, enabled):
        self.coils[address] = bool(enabled)
        self.writes.append((address, bool(enabled)))


def driver(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "true")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2")
    return WaveshareModbusDriver(client=FakeClient())


def test_arbitrary_relay_on_is_blocked_before_release(monkeypatch):
    subject = driver(monkeypatch)
    subject.direct_relay_readiness_provider = lambda: {
        "state": "FIELD_CERTIFICATION_REQUIRED"
    }

    with pytest.raises(RuntimeError, match="READY_FOR_RELEASE"):
        subject.set_relay(8, True)

    assert subject.client.writes == []


def test_arbitrary_relay_on_is_allowed_only_after_release_gate(monkeypatch):
    subject = driver(monkeypatch)
    subject.direct_relay_readiness_provider = lambda: {
        "state": "READY_FOR_RELEASE"
    }

    subject.set_relay(8, True)

    assert subject.client.writes == [(7, True)]


def test_arbitrary_relay_off_remains_available_when_gate_is_broken(monkeypatch):
    subject = driver(monkeypatch)
    subject.client.coils[7] = True

    def broken():
        raise RuntimeError("database unavailable")

    subject.direct_relay_readiness_provider = broken
    subject.set_relay(8, False)

    assert subject.client.coils[7] is False
