import unittest
from datetime import datetime, timedelta, timezone

from app.geocooling.thermal import ThermalEngine


class ThermalEngineTests(unittest.TestCase):
    def test_metrics_and_power(self) -> None:
        engine = ThermalEngine()
        engine.default_flow_rate_l_min = 20.0
        now = datetime.now(timezone.utc)
        engine.ingest({
            "timestamp": (now - timedelta(minutes=30)).isoformat(),
            "indoor_temperature_c": 25.0,
            "floor_supply_temperature_c": 18.0,
            "floor_return_temperature_c": 20.0,
        })
        result = engine.ingest({
            "timestamp": now.isoformat(),
            "indoor_temperature_c": 24.5,
            "floor_supply_temperature_c": 18.0,
            "floor_return_temperature_c": 20.5,
        })
        self.assertTrue(result["available"])
        self.assertEqual(result["floor_delta_t_c"], 2.5)
        self.assertGreater(result["cooling_power_kw"], 0)
        self.assertLess(result["trends_c_per_hour"]["indoor_30m"], 0)

    def test_humidity_validation(self) -> None:
        engine = ThermalEngine()
        with self.assertRaises(ValueError):
            engine.ingest({"indoor_humidity_percent": 120})


if __name__ == "__main__":
    unittest.main()
