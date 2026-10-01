import time
import unittest
from datetime import datetime, timezone, timedelta
from trading_bot.news_filter import EconomicNewsFilter


class TestEconomicNewsFilter(unittest.TestCase):
    def setUp(self):
        self.news_filter = EconomicNewsFilter(
            target_currencies=["USD"],
            freeze_before_mins=15,
            freeze_after_mins=15
        )

    def test_news_freeze_window(self):
        # Create a synthetic NFP event at 12:30 UTC
        event_time = datetime(2026, 9, 4, 12, 30, 0, tzinfo=timezone.utc)
        self.news_filter.cached_high_impact_events = [
            {
                "title": "Non-Farm Employment Change",
                "country": "USD",
                "impact": "High",
                "time_utc": event_time,
                "timestamp": int(event_time.timestamp())
            }
        ]
        self.news_filter.last_fetch_time = time.time()

        # 1. 20 minutes before (12:10 UTC) -> Should NOT freeze
        time_1210 = datetime(2026, 9, 4, 12, 10, 0, tzinfo=timezone.utc)
        is_frozen, reason, _ = self.news_filter.is_news_freeze_active(time_1210)
        self.assertFalse(is_frozen)

        # 2. 10 minutes before (12:20 UTC) -> MUST freeze
        time_1220 = datetime(2026, 9, 4, 12, 20, 0, tzinfo=timezone.utc)
        is_frozen, reason, ev = self.news_filter.is_news_freeze_active(time_1220)
        self.assertTrue(is_frozen)
        self.assertIn("Non-Farm Employment Change", reason)

        # 3. 5 minutes after (12:35 UTC) -> MUST freeze (cooldown)
        time_1235 = datetime(2026, 9, 4, 12, 35, 0, tzinfo=timezone.utc)
        is_frozen, reason, ev = self.news_filter.is_news_freeze_active(time_1235)
        self.assertTrue(is_frozen)
        self.assertIn("Cooldown active", reason)

        # 4. 20 minutes after (12:50 UTC) -> Should NOT freeze (spreads normalized)
        time_1250 = datetime(2026, 9, 4, 12, 50, 0, tzinfo=timezone.utc)
        is_frozen, reason, _ = self.news_filter.is_news_freeze_active(time_1250)
        self.assertFalse(is_frozen)


if __name__ == "__main__":
    unittest.main()
