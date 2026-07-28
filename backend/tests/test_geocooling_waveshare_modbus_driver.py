import pytest

from app.geocooling.waveshare_modbus_driver import WaveshareModbusDriver


class FakeClient:
    def __init__(self):
        self.coils = {}
        self.writes = []

    def read_coil(self, address):
        return bool(self.coils.get(address, False))

    def write_coil(self, address, enabled):
        self.coils[address] = enabled
        self.writes.append((address, enabled))


def build_driver(monkeypatch, armed="false"):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", armed)
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2")
    return WaveshareModbusDriver(client=FakeClient())


def test_driver_is_disarmed_by_default(monkeypatch):
    driver = build_driver(monkeypatch)
    with pytest.raises(RuntimeError, match="désarmé"):
        driver.open_valve()
    with pytest.raises(RuntimeError, match="désarmé"):
        driver.start_pump()


def test_off_commands_remain_allowed_when_disarmed(monkeypatch):
    driver = build_driver(monkeypatch)
    driver.client.coils = {0: True, 1: True}
    driver.force_safe_state()
    assert driver.client.coils == {0: False, 1: False}


def test_pump_requires_valve_feedback(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    with pytest.raises(RuntimeError, match="vanne est OFF"):
        driver.start_pump()


def test_safe_start_and_stop_sequence(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    driver.open_valve()
    driver.start_pump()
    assert driver.status()["valve_open"] is True
    assert driver.status()["pump_running"] is True
    driver.force_safe_state()
    assert driver.status()["valve_open"] is False
    assert driver.status()["pump_running"] is False
    assert driver.client.writes == [(0, True), (1, True), (1, False), (0, False)]


def test_relay_mapping_is_configurable(monkeypatch):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", "true")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_ADDRESS_BASE", "0")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "4")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "7")
    client = FakeClient()
    driver = WaveshareModbusDriver(client=client)
    driver.open_valve()
    driver.start_pump()
    assert client.writes == [(3, True), (6, True)]
