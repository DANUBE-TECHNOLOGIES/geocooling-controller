import time
import unittest

from app.automation.models import AutomationAction, AutomationMode
from app.automation.service import AutomationService


class FakeRepository:
    def __init__(self): self.items = {}
    def initialize(self): pass
    def save(self, item): self.items[item.execution_id] = item.to_dict()
    def get(self, execution_id): return self.items.get(execution_id)
    def list(self, limit=100, state=None):
        values = list(self.items.values())
        return [v for v in values if not state or v["state"] == state][:limit]


class FakeBus:
    def __init__(self): self.events = []
    def publish(self, event_type, source, payload=None, priority="info", correlation_id=None):
        self.events.append((event_type, payload or {}))
        return "event-id"


class FakeDevices:
    def __init__(self, online=False): self.online = online
    def get_device(self, device_id):
        return {"device_id": device_id, "status": "online" if self.online else "offline"}


class FakeController:
    def __init__(self): self.started = 0; self.stopped = 0
    def request_start(self): self.started += 1; return {"accepted": True, "message": "started"}
    def request_stop(self): self.stopped += 1; return {"accepted": True, "message": "stopped"}
    def emergency_stop(self): return {"accepted": True, "message": "emergency"}


def wait_terminal(service, execution_id):
    for _ in range(100):
        item = service.get(execution_id)
        if item and item["state"] in {"success", "failed", "rejected", "cancelled"}:
            return item
        time.sleep(0.01)
    raise AssertionError("automation did not finish")


class AutomationServiceTests(unittest.TestCase):
    def make_service(self, online=False):
        service = AutomationService(None, FakeBus(), FakeDevices(online), FakeController())
        service.repository = FakeRepository()
        service.start()
        return service

    def test_simulation_runs_when_device_offline(self):
        service = self.make_service(False)
        item = service.create("geocooling", AutomationAction.START, AutomationMode.SIMULATION)
        result = wait_terminal(service, item.execution_id)
        self.assertEqual(result["state"], "success")
        self.assertEqual(service.geocooling_controller.started, 1)

    def test_real_mode_rejected_when_device_offline(self):
        service = self.make_service(False)
        item = service.create("geocooling", AutomationAction.START, AutomationMode.REAL)
        result = wait_terminal(service, item.execution_id)
        self.assertEqual(result["state"], "rejected")
        self.assertIn("hors ligne", result["message"])


if __name__ == "__main__":
    unittest.main()
