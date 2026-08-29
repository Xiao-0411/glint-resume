import datetime
import unittest

from app.core.security import next_daily_auth_reset


class AuthResetTests(unittest.TestCase):
    def test_before_beijing_four_uses_same_day_boundary(self):
        # 03:30 Beijing = 19:30 UTC on the previous calendar day.
        now = datetime.datetime(2026, 8, 28, 19, 30, tzinfo=datetime.timezone.utc)
        self.assertEqual(
            next_daily_auth_reset(now),
            datetime.datetime(2026, 8, 28, 20, 0, tzinfo=datetime.timezone.utc),
        )

    def test_at_or_after_beijing_four_uses_next_day_boundary(self):
        now = datetime.datetime(2026, 8, 29, 1, 0, tzinfo=datetime.timezone.utc)
        self.assertEqual(
            next_daily_auth_reset(now),
            datetime.datetime(2026, 8, 29, 20, 0, tzinfo=datetime.timezone.utc),
        )


if __name__ == "__main__":
    unittest.main()
