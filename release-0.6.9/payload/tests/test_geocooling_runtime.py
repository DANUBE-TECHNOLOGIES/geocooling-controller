import unittest
from datetime import datetime, timedelta, timezone

from app.geocooling.runtime import RuntimeGuards


class RuntimeGuardsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.now = datetime(2026, 7, 24, 12, 0, tzinfo=timezone.utc)
        self.guards = RuntimeGuards(minimum_on_seconds=300, minimum_off_seconds=180)

    def test_start_is_blocked_during_minimum_off_time(self) -> None:
        decision = self.guards.can_start(
            stopped_at=self.now - timedelta(seconds=60), now=self.now
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.remaining_seconds, 120)

    def test_start_is_allowed_after_minimum_off_time(self) -> None:
        decision = self.guards.can_start(
            stopped_at=self.now - timedelta(seconds=181), now=self.now
        )
        self.assertTrue(decision.allowed)

    def test_stop_is_blocked_during_minimum_on_time(self) -> None:
        decision = self.guards.can_stop(
            started_at=self.now - timedelta(seconds=120), now=self.now
        )
        self.assertFalse(decision.allowed)
        self.assertEqual(decision.remaining_seconds, 180)

    def test_stop_is_allowed_after_minimum_on_time(self) -> None:
        decision = self.guards.can_stop(
            started_at=self.now - timedelta(seconds=301), now=self.now
        )
        self.assertTrue(decision.allowed)


if __name__ == "__main__":
    unittest.main()
