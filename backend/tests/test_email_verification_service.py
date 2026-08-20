import datetime
import unittest
from types import SimpleNamespace
from unittest.mock import PropertyMock, patch

from app.services import email_verification_service as service


class FakeQuery:
    def __init__(self, result):
        self.result = result

    def filter(self, *args):
        return self

    def order_by(self, *args):
        return self

    def first(self):
        return self.result


class FakeDB:
    def __init__(self, latest=None):
        self.latest = latest
        self.added = []
        self.commit_count = 0

    def query(self, model):
        return FakeQuery(self.latest)

    def add(self, row):
        self.added.append(row)

    def commit(self):
        self.commit_count += 1


class EmailVerificationTimeTests(unittest.TestCase):
    def setUp(self):
        self.now = datetime.datetime(2026, 8, 19, 6, 30, 0)

    def test_naive_mysql_timestamp_enforces_resend_cooldown(self):
        latest = SimpleNamespace(sent_at=self.now - datetime.timedelta(seconds=10))
        db = FakeDB(latest)

        with (
            patch.object(service, "_utcnow_naive", return_value=self.now),
            patch.object(service.settings, "EMAIL_CODE_COOLDOWN_SECONDS", 60),
        ):
            with self.assertRaises(service.EmailCodeCooldownError) as raised:
                service.create_and_send_code(db, "user@example.com")

        self.assertEqual(raised.exception.retry_after, 50)
        self.assertEqual(db.added, [])
        self.assertEqual(db.commit_count, 0)

    def test_send_persists_utc_naive_timestamps_after_cooldown(self):
        latest = SimpleNamespace(sent_at=self.now - datetime.timedelta(seconds=61))
        db = FakeDB(latest)

        with (
            patch.object(service, "_utcnow_naive", return_value=self.now),
            patch.object(service.settings, "EMAIL_CODE_COOLDOWN_SECONDS", 60),
            patch.object(service.settings, "EMAIL_CODE_EXPIRE_MINUTES", 10),
            patch.object(service.settings, "EMAIL_VERIFICATION_DEV_MODE", True),
            patch.object(
                type(service.settings),
                "smtp_available",
                new_callable=PropertyMock,
                return_value=False,
            ),
            patch.object(service.secrets, "randbelow", return_value=123456),
        ):
            result = service.create_and_send_code(db, "User@Example.com")

        self.assertEqual(result["dev_code"], "123456")
        self.assertEqual(db.commit_count, 1)
        self.assertEqual(len(db.added), 1)
        self.assertEqual(db.added[0].email, "user@example.com")
        self.assertEqual(db.added[0].sent_at, self.now)
        self.assertEqual(
            db.added[0].expires_at,
            self.now + datetime.timedelta(minutes=10),
        )
        self.assertIsNone(db.added[0].sent_at.tzinfo)
        self.assertIsNone(db.added[0].expires_at.tzinfo)

    def test_aware_timestamp_is_normalized_before_cooldown_math(self):
        beijing = datetime.timezone(datetime.timedelta(hours=8))
        sent_at = (self.now - datetime.timedelta(seconds=20)).replace(
            tzinfo=datetime.timezone.utc
        ).astimezone(beijing)
        db = FakeDB(SimpleNamespace(sent_at=sent_at))

        with (
            patch.object(service, "_utcnow_naive", return_value=self.now),
            patch.object(service.settings, "EMAIL_CODE_COOLDOWN_SECONDS", 60),
        ):
            with self.assertRaises(service.EmailCodeCooldownError) as raised:
                service.create_and_send_code(db, "user@example.com")

        self.assertEqual(raised.exception.retry_after, 40)


if __name__ == "__main__":
    unittest.main()
