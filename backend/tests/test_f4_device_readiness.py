from app.geocooling.device_manager import DeviceManager


class FakeDriver:
    def __init__(self, status):
        self._status = status

    def status(self):
        return self._status


def waveshare_status(*, connected=True, armed=True, ev=1, pumps=2):
    return {
        "driver": "waveshare_modbus",
        "simulation": False,
        "connected": connected,
        "armed": armed,
        "topology": {
            "ev": "valve_relay",
            "m11_m13": "pump_relay_shared",
        },
        "device": {
            "ev_relay": ev,
            "m11_m13_relay": pumps,
        },
    }


def test_f4_readiness_names_physical_actuators():
    status = DeviceManager(FakeDriver(waveshare_status())).status()
    assert status["ready"] is True
    assert status["topology_valid"] is True
    assert status["actuators"]["ev"]["label"] == "EV"
    assert status["actuators"]["m11_m13"]["label"] == "M11+M13"
    assert status["safe_state"] == "M11+M13 OFF puis EV CLOSED"


def test_f4_readiness_requires_explicit_arm():
    status = DeviceManager(FakeDriver(waveshare_status(armed=False))).status()
    assert status["ready"] is False
    assert status["connected"] is True
    assert "désarmé" in status["reason"]


def test_f4_readiness_rejects_invalid_shared_mapping():
    status = DeviceManager(FakeDriver(waveshare_status(ev=1, pumps=1))).status()
    assert status["ready"] is False
    assert status["topology_valid"] is False
    assert "Topologie" in status["reason"]
