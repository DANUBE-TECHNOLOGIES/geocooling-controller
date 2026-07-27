import os
import unittest
from unittest.mock import patch

from app.geocooling.safety import GeoCoolingSafetyManager


class GeoCoolingSafetyTests(unittest.TestCase):
    def test_dew_point_is_calculated(self) -> None:
        value = GeoCoolingSafetyManager.dew_point_c(24.0, 60.0)
        self.assertAlmostEqual(value, 15.76, places=1)

    def test_safe_margin_is_accepted(self) -> None:
        manager = GeoCoolingSafetyManager()
        decision = manager.evaluate(
            indoor_temperature_c=24.0,
            indoor_humidity_percent=50.0,
            surface_temperature_c=20.0,
        )
        self.assertTrue(decision.safe)
        self.assertEqual(decision.level, "safe")

    def test_condensation_risk_is_blocked(self) -> None:
        manager = GeoCoolingSafetyManager()
        decision = manager.evaluate(
            indoor_temperature_c=24.0,
            indoor_humidity_percent=70.0,
            surface_temperature_c=18.0,
        )
        self.assertFalse(decision.safe)
        self.assertEqual(decision.level, "condensation_risk")

    def test_missing_sensors_can_be_required(self) -> None:
        with patch.dict(
            os.environ,
            {"GEOCOOLING_REQUIRE_THERMAL_SENSORS": "true"},
        ):
            manager = GeoCoolingSafetyManager()
        decision = manager.evaluate(
            indoor_temperature_c=None,
            indoor_humidity_percent=None,
            surface_temperature_c=None,
        )
        self.assertFalse(decision.safe)
        self.assertEqual(decision.level, "blocked")

    def test_invalid_humidity_is_rejected(self) -> None:
        manager = GeoCoolingSafetyManager()
        decision = manager.evaluate(
            indoor_temperature_c=24.0,
            indoor_humidity_percent=0.0,
            surface_temperature_c=20.0,
        )
        self.assertFalse(decision.safe)
        self.assertEqual(decision.level, "invalid")


if __name__ == "__main__":
    unittest.main()
