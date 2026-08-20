import unittest
from types import SimpleNamespace
from unittest.mock import patch

from pydantic import ValidationError
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.core.database import Base
from app.core.config import _validate_auth_secret
from app.models.db_models import Resume, Session, User
from app.models.schemas import ChatRequest, EvaluateResumeRequest, EvaluateTextRequest
from app.store import db_store
from app.store.db_store import SessionStore


class SessionOwnershipTests(unittest.TestCase):
    def setUp(self):
        engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(engine)
        self.local_session = sessionmaker(bind=engine)
        self.store = SessionStore()

    def seed(self, *rows):
        db = self.local_session()
        try:
            db.add_all(rows)
            db.commit()
        finally:
            db.close()

    def test_different_user_cannot_claim_existing_session(self):
        self.seed(
            User(id="user-a"),
            User(id="user-b"),
            Session(id="session-a", user_id="user-a"),
        )

        with patch.object(db_store, "SessionLocal", self.local_session):
            with self.assertRaises(PermissionError):
                self.store.get_or_create("session-a", user_id="user-b")

        db = self.local_session()
        try:
            self.assertEqual(db.get(Session, "session-a").user_id, "user-a")
        finally:
            db.close()

    def test_explicit_attach_moves_anonymous_session_and_resumes(self):
        self.seed(
            User(id="anonymous"),
            User(id="user-b"),
            Session(id="guest-session", user_id="anonymous"),
            Resume(
                user_id="anonymous",
                session_id="guest-session",
                resume_json={},
                quality_report_json={},
            ),
        )

        with patch.object(db_store, "SessionLocal", self.local_session):
            self.store.attach_to_user("guest-session", "user-b")

        db = self.local_session()
        try:
            self.assertEqual(db.get(Session, "guest-session").user_id, "user-b")
            self.assertEqual(db.query(Resume).one().user_id, "user-b")
        finally:
            db.close()


class RequestLimitTests(unittest.TestCase):
    def test_chat_message_and_session_are_bounded(self):
        with self.assertRaises(ValidationError):
            ChatRequest(session_id="s", user_message="x" * 4001, user_msg_count=1)

    def test_evaluate_text_is_bounded(self):
        with self.assertRaises(ValidationError):
            EvaluateTextRequest(text="x" * 100001)

    def test_resume_nested_values_are_bounded(self):
        with self.assertRaises(ValidationError):
            EvaluateResumeRequest(resume={"experiences": ["x" * 20001]})


class ProductionConfigTests(unittest.TestCase):
    def test_production_rejects_short_auth_secret(self):
        config = SimpleNamespace(
            AUTH_SECRET_KEY="too-short",
            is_production=True,
            has_public_origin=True,
        )
        with self.assertRaises(RuntimeError):
            _validate_auth_secret(config)


if __name__ == "__main__":
    unittest.main()
