import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
import unittest
from datetime import datetime, timezone

from analytics_demo import build_summary


class AnalyticsSummaryTests(unittest.TestCase):
    def test_empty_activity_returns_zero_metrics(self):
        since = datetime(2026, 10, 12, tzinfo=timezone.utc)
        result = build_summary([], 0, since)

        self.assertEqual(result["total_checks"], 0)
        self.assertEqual(result["high_alerts"], 0)
        self.assertEqual(result["review_alerts"], 0)
        self.assertEqual(len(result["daily_activity"]), 7)

    def test_alert_counts_and_daily_activity(self):
        since = datetime(2026, 10, 12, tzinfo=timezone.utc)
        rows = [
            {
                "created_at": "2026-10-18T08:00:00+00:00",
                "alert_count": 2,
                "high_alert_count": 1,
                "review_alert_count": 1,
                "duplicate_alert_count": 1,
                "unresolved_count": 2,
            },
            {
                "created_at": "2026-10-18T09:00:00+00:00",
                "alert_count": 1,
                "high_alert_count": 0,
                "review_alert_count": 1,
                "duplicate_alert_count": 0,
                "unresolved_count": 1,
            },
        ]

        result = build_summary(rows, 5, since)

        self.assertEqual(result["total_checks"], 5)
        self.assertEqual(result["high_alerts"], 1)
        self.assertEqual(result["review_alerts"], 2)
        self.assertEqual(result["duplicate_alerts"], 1)
        self.assertEqual(result["unresolved_names"], 3)
        self.assertEqual(result["daily_activity"][-1]["checks"], 2)
        self.assertEqual(len(result["recent_activity"]), 2)


if __name__ == "__main__":
    unittest.main()
