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


class FailingTargetedClient(FakeClient):
    """Simule un échec ciblé puis permet le repli relais par relais."""

    def __init__(self):
        super().__init__()
        self.fail_next = True

    def write_coil(self, address, enabled):
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("échec ciblé")
        super().write_coil(address, enabled)


def build_driver(monkeypatch, armed="false", client=None):
    monkeypatch.setenv("GEOCOOLING_HARDWARE_ARMED", armed)
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_VALVE_RELAY", "1")
    monkeypatch.setenv("GEOCOOLING_WAVESHARE_PUMP_RELAY", "2")
    return WaveshareModbusDriver(client=client or FakeClient())


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


def test_pump_requires_ev_feedback(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    with pytest.raises(RuntimeError, match="EV est OFF"):
        driver.start_pump()


def test_safe_start_and_stop_sequence(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    driver.open_valve()
    driver.start_pump()
    status = driver.status()
    assert status["valve_open"] is True
    assert status["pump_running"] is True
    assert status["ev_open"] is True
    assert status["m11_m13_running"] is True
    driver.force_safe_state()
    status = driver.status()
    assert status["valve_open"] is False
    assert status["pump_running"] is False
    assert status["ev_open"] is False
    assert status["m11_m13_running"] is False
    assert driver.client.writes == [(0, True), (1, True), (1, False), (0, False)]


def test_shared_m11_m13_mapping_is_explicit(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    status = driver.status()
    assert status["device"]["ev_relay"] == 1
    assert status["device"]["m11_m13_relay"] == 2
    assert status["topology"]["m11_m13"] == "pump_relay_shared"


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


def test_generic_relay_on_requires_arming(monkeypatch):
    driver = build_driver(monkeypatch)
    with pytest.raises(RuntimeError, match="désarmé"):
        driver.set_relay(8, True)
    driver.set_relay(8, False)


def test_read_all_eight_relays(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    driver.client.coils = {0: True, 3: True, 7: True}
    states = driver.read_relays()
    assert states == [True, False, False, True, False, False, False, True]
    assert driver.status()["relays"][7] == {"relay": 8, "address": 7, "on": True}


def test_all_off_cuts_every_relay(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    driver.client.coils = {index: True for index in range(8)}
    driver.all_off()
    assert all(not value for value in driver.client.coils.values())


def test_force_safe_state_falls_back_to_global_shutdown(monkeypatch):
    client = FailingTargetedClient()
    client.coils = {0: True, 1: True, 2: True}
    driver = build_driver(monkeypatch, armed="true", client=client)
    driver.force_safe_state()
    assert all(not value for value in client.coils.values())


def test_invalid_relay_number_is_rejected(monkeypatch):
    driver = build_driver(monkeypatch, armed="true")
    with pytest.raises(ValueError, match="1 et 8"):
        driver.set_relay(9, False)
