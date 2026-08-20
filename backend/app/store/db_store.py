"""
MySQL-backed SessionStore.

The public methods intentionally match memory_store.py so existing service code
keeps working while conversation messages and generated resumes persist.
"""
import datetime
from typing import Any, Dict, List, Optional

from sqlalchemy import or_

from app.core.database import SessionLocal
from app.models.db_models import Message, Resume, Session, User


class SessionStore:
    """Database-backed storage for sessions, messages, and resumes."""

    ANONYMOUS_USER_ID = "anonymous"

    def get_or_create(
        self,
        session_id: str,
        target_job: str = "",
        user_id: Optional[str] = None,
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            sess = db.query(Session).filter(Session.id == session_id).first()
            if sess is None:
                self._ensure_user(db, owner_id)
                sess = Session(id=session_id, user_id=owner_id, target_job=target_job)
                db.add(sess)
                db.commit()
                db.refresh(sess)
            else:
                self._assert_owner(sess, owner_id)
                changed = False
                if target_job and not sess.target_job:
                    sess.target_job = target_job
                    changed = True
                if changed:
                    sess.updated_at = self._now()
                    db.commit()
                    db.refresh(sess)
            return self._to_dict(sess)
        finally:
            db.close()

    def get(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            sess = (
                db.query(Session)
                .filter(
                    Session.id == session_id,
                    Session.user_id == self._owner_id(user_id),
                )
                .first()
            )
            if sess is None:
                return None
            return self._to_dict(sess)
        finally:
            db.close()

    def get_for_user(self, session_id: str, user_id: str) -> Optional[Dict[str, Any]]:
        return self.get(session_id, user_id=user_id)

    def get_latest_for_user(self, user_id: str) -> Optional[Dict[str, Any]]:
        db = SessionLocal()
        try:
            sess = (
                db.query(Session)
                .filter(Session.user_id == user_id)
                .order_by(Session.updated_at.desc(), Session.created_at.desc())
                .first()
            )
            if sess is None:
                return None
            return self._to_dict(sess)
        finally:
            db.close()

    def attach_to_user(
        self,
        session_id: str,
        user_id: str,
        target_job: str = "",
    ) -> Dict[str, Any]:
        db = SessionLocal()
        try:
            self._ensure_user(db, user_id)
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )
            if sess is None:
                sess = Session(id=session_id, user_id=user_id, target_job=target_job)
                db.add(sess)
            else:
                owner_id = sess.user_id
                if owner_id and owner_id not in (self.ANONYMOUS_USER_ID, user_id):
                    raise PermissionError("Session belongs to another user")
                sess.user_id = user_id
                if target_job and not sess.target_job:
                    sess.target_job = target_job
                sess.updated_at = self._now()

                if owner_id in (None, self.ANONYMOUS_USER_ID):
                    db.query(Resume).filter(
                        Resume.session_id == session_id,
                        or_(
                            Resume.user_id.is_(None),
                            Resume.user_id == self.ANONYMOUS_USER_ID,
                        ),
                    ).update({Resume.user_id: user_id}, synchronize_session=False)
            db.commit()
            db.refresh(sess)
            return self._to_dict(sess)
        finally:
            db.close()

    def append_message(
        self,
        session_id: str,
        role: str,
        content: str,
        user_id: Optional[str] = None,
    ):
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )
            if sess is None:
                self._ensure_user(db, owner_id)
                sess = Session(id=session_id, user_id=owner_id)
                db.add(sess)
                db.flush()
            else:
                self._assert_owner(sess, owner_id)

            db.add(Message(session_id=session_id, role=role, content=content))
            sess.updated_at = self._now()
            db.commit()
        finally:
            db.close()

    def set_stage(
        self,
        session_id: str,
        stage: str,
        user_id: Optional[str] = None,
    ):
        db = SessionLocal()
        try:
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )
            if sess:
                self._assert_owner(sess, self._owner_id(user_id))
                sess.stage = stage
                sess.updated_at = self._now()
                db.commit()
        finally:
            db.close()

    def update_extracted(
        self,
        session_id: str,
        info: Dict[str, Any],
        user_id: Optional[str] = None,
    ):
        db = SessionLocal()
        try:
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )
            if sess:
                self._assert_owner(sess, self._owner_id(user_id))
                current = dict(sess.extracted or {})
                current.update(info)
                sess.extracted = current
                sess.updated_at = self._now()
                db.commit()
        finally:
            db.close()

    def list_sessions(self, user_id: Optional[str] = None) -> List[str]:
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            return [
                row.id
                for row in db.query(Session.id).filter(Session.user_id == owner_id).all()
            ]
        finally:
            db.close()

    def reset(self, session_id: str, user_id: Optional[str] = None):
        db = SessionLocal()
        try:
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )
            if sess:
                self._assert_owner(sess, self._owner_id(user_id))
                db.delete(sess)
                db.commit()
        finally:
            db.close()

    def save_resume(
        self,
        session_id: str,
        resume_json: Dict,
        quality_report_json: Dict,
        target_job: str = "",
        source: str = "chat",
        user_id: Optional[str] = None,
    ):
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            sess = (
                db.query(Session)
                .filter(Session.id == session_id)
                .with_for_update()
                .first()
            )

            if sess is None:
                self._ensure_user(db, owner_id)
                sess = Session(id=session_id, user_id=owner_id, target_job=target_job)
                db.add(sess)
                db.flush()
            else:
                self._assert_owner(sess, owner_id)
                if target_job and not sess.target_job:
                    sess.target_job = target_job

            total_score = quality_report_json.get("total_score", 0) if quality_report_json else 0
            grade = quality_report_json.get("grade", "") if quality_report_json else ""
            resume = Resume(
                user_id=owner_id,
                session_id=session_id,
                target_job=target_job,
                resume_json=resume_json,
                quality_report_json=quality_report_json,
                total_score=total_score,
                grade=grade,
                source=source,
            )
            db.add(resume)
            sess.updated_at = self._now()
            db.commit()
            db.refresh(resume)
            return resume.id
        finally:
            db.close()

    def get_resumes_by_session(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> List[Dict]:
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            rows = (
                db.query(Resume)
                .filter(
                    Resume.session_id == session_id,
                    Resume.user_id == owner_id,
                )
                .order_by(Resume.created_at.desc())
                .all()
            )
            return [self._resume_to_dict(row) for row in rows]
        finally:
            db.close()

    def get_latest_resume(
        self,
        session_id: str,
        user_id: Optional[str] = None,
    ) -> Optional[Dict]:
        db = SessionLocal()
        try:
            owner_id = self._owner_id(user_id)
            row = (
                db.query(Resume)
                .filter(
                    Resume.session_id == session_id,
                    Resume.user_id == owner_id,
                )
                .order_by(Resume.created_at.desc())
                .first()
            )
            if row is None:
                return None
            return self._resume_to_dict(row)
        finally:
            db.close()

    def get_latest_resume_for_user(self, user_id: str) -> Optional[Dict]:
        db = SessionLocal()
        try:
            row = (
                db.query(Resume)
                .filter(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc())
                .first()
            )
            if row is None:
                return None
            return self._resume_to_dict(row)
        finally:
            db.close()

    def get_resumes_for_user(self, user_id: str, limit: int = 30) -> List[Dict]:
        db = SessionLocal()
        try:
            rows = (
                db.query(Resume)
                .filter(Resume.user_id == user_id)
                .order_by(Resume.created_at.desc(), Resume.id.desc())
                .limit(max(1, min(limit, 100)))
                .all()
            )
            return [self._resume_to_dict(row) for row in rows]
        finally:
            db.close()

    def get_resume_for_user(self, resume_id: int, user_id: str) -> Optional[Dict]:
        db = SessionLocal()
        try:
            row = (
                db.query(Resume)
                .filter(Resume.id == resume_id, Resume.user_id == user_id)
                .first()
            )
            if row is None:
                return None
            return self._resume_to_dict(row)
        finally:
            db.close()

    def delete_resume_for_user(self, resume_id: int, user_id: str) -> bool:
        db = SessionLocal()
        try:
            row = (
                db.query(Resume)
                .filter(Resume.id == resume_id, Resume.user_id == user_id)
                .first()
            )
            if row is None:
                return False
            db.delete(row)
            db.commit()
            return True
        finally:
            db.close()

    def _to_dict(self, sess: Session) -> Dict[str, Any]:
        return {
            "session_id": sess.id,
            "user_id": sess.user_id,
            "target_job": sess.target_job,
            "created_at": sess.created_at.timestamp() if sess.created_at else 0,
            "messages": [
                {"role": message.role, "content": message.content}
                for message in sess.messages
            ],
            "stage": sess.stage,
            "extracted": sess.extracted or {},
        }

    def _resume_to_dict(self, resume: Resume) -> Dict:
        return {
            "id": resume.id,
            "user_id": resume.user_id,
            "session_id": resume.session_id,
            "target_job": resume.target_job,
            "resume": resume.resume_json,
            "quality_report": resume.quality_report_json,
            "total_score": resume.total_score,
            "grade": resume.grade,
            "source": resume.source,
            "created_at": resume.created_at.isoformat() if resume.created_at else None,
        }

    def _ensure_user(self, db, user_id: str):
        user = db.query(User).filter(User.id == user_id).first()
        if user is None:
            display_name = "匿名用户" if user_id == self.ANONYMOUS_USER_ID else ""
            db.add(User(id=user_id, display_name=display_name))
            db.flush()

    def _owner_id(self, user_id: Optional[str]) -> str:
        return user_id if user_id is not None else self.ANONYMOUS_USER_ID

    def _assert_owner(self, session: Session, owner_id: str):
        if session.user_id != owner_id:
            raise PermissionError("Session belongs to another user")

    def _now(self):
        return datetime.datetime.now(datetime.timezone.utc)


session_store = SessionStore()
