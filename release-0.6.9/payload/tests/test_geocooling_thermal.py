import unittest
from datetime import datetime, timedelta, timezone
from unittest.mock import patch

from app.geocooling.thermal import ThermalEstimator, ThermalSample


class ThermalEstimatorTests(unittest.TestCase):
    def test_derived_temperatures_are_calculated(self) -> None:
        estimator = ThermalEstimator()
        result = estimator.update(
            indoor_temperature_c=24.0,
            indoor_humidity_percent=60.0,
            surface_temperature_c=20.0,
            floor_supply_temperature_c=18.0,
            floor_return_temperature_c=20.5,
            source_inlet_temperature_c=12.0,
            source_outlet_temperature_c=15.0,
            outdoor_temperature_c=31.0,
        )
        derived = result["derived"]
        self.assertAlmostEqual(derived["dew_point_c"], 15.8, places=1)
        self.assertEqual(derived["floor_delta_t_c"], 2.5)
        self.assertEqual(derived["source_delta_t_c"], 3.0)
        self.assertTrue(derived["cooling_exchange_detected"])

    def test_trend_is_calculated(self) -> None:
        estimator = ThermalEstimator()
        now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        estimator._samples.append(ThermalSample(captured_at=now, indoor_temperature_c=25.0))
        estimator._samples.append(ThermalSample(captured_at=now + timedelta(minutes=30), indoor_temperature_c=24.5))
        result = estimator.status()
        self.assertEqual(result["derived"]["indoor_temperature_trend_c_per_hour"], -1.0)
        self.assertEqual(result["derived"]["thermal_state"], "cooling")

    def test_empty_estimator_is_unavailable(self) -> None:
        self.assertFalse(ThermalEstimator().status()["available"])


if __name__ == "__main__":
    unittest.main()
