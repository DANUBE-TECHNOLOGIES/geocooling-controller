from __future__ import annotations

import importlib
import os
import unittest


class AppContractTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        os.environ.setdefault(
            "DATABASE_URL",
            "postgresql+psycopg://test:test@postgres:5432/test",
        )
        cls.main = importlib.import_module("app.main")
        cls.routes = {
            (method, route.path)
            for route in cls.main.app.routes
            for method in getattr(route, "methods", set())
        }

    def test_version(self) -> None:
        self.assertEqual(self.main.APP_VERSION, "0.6.5")

    def test_critical_routes_are_registered(self) -> None:
        expected = {
            ("GET", "/health/live"),
            ("GET", "/building/state"),
            ("GET", "/automation/diagnostics"),
            ("GET", "/rules/diagnostics"),
            ("POST", "/rules/evaluate"),
            ("DELETE", "/rules/{rule_id}"),
        }
        self.assertTrue(expected.issubset(self.routes), expected - self.routes)

    def test_no_204_route_declares_response_body(self) -> None:
        for route in self.main.app.routes:
            if getattr(route, "status_code", None) == 204:
                self.assertIsNone(getattr(route, "response_model", None))


if __name__ == "__main__":
    unittest.main()
