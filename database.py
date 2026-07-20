import enum
import os
import secrets
from datetime import datetime, timezone

from dotenv import load_dotenv
from sqlalchemy import (
    Column, DateTime, Enum, Float, ForeignKey, Integer, String, Text, create_engine
)
from sqlalchemy.orm import DeclarativeBase, Session, relationship, sessionmaker

load_dotenv()


def utcnow() -> datetime:
    """Naive UTC timestamp — the non-deprecated replacement for datetime.utcnow().

    Columns store naive datetimes, and several endpoints compare them directly
    (e.g. `now >= session.created_at + delay`), so we deliberately strip tzinfo to
    keep every stored/compared value naive-UTC and avoid aware/naive TypeErrors.
    """
    return datetime.now(timezone.utc).replace(tzinfo=None)

DATABASE_URL = os.getenv("DATABASE_URL", "sqlite:///./cogprint.db")
engine = create_engine(DATABASE_URL, connect_args={"check_same_thread": False})
SessionLocal = sessionmaker(autocommit=False, autoflush=False, bind=engine)


class Base(DeclarativeBase):
    pass


class StudyTechnique(str, enum.Enum):
    SPACED_REPETITION = "spaced_repetition"
    ACTIVE_RECALL = "active_recall"
    RE_READING = "re_reading"
    MIND_MAPS = "mind_maps"
    INTERLEAVING = "interleaving"
    ELABORATIVE_INTERROGATION = "elaborative_interrogation"
    PRACTICE_TESTING = "practice_testing"


class TimeOfDay(str, enum.Enum):
    MORNING = "morning"
    AFTERNOON = "afternoon"
    EVENING = "evening"
    NIGHT = "night"


class StudyGroup(str, enum.Enum):
    CONTROL = "control"
    TREATMENT = "treatment"


# Unambiguous alphabet for share codes (no 0/O/1/I/L) so buddies can type them.
_SHARE_ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"


def generate_share_code(length: int = 6) -> str:
    """Short, human-typable, URL-safe buddy code (see #9 in COGPRINT_IDEAS.md)."""
    return "".join(secrets.choice(_SHARE_ALPHABET) for _ in range(length))


class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    group = Column(Enum(StudyGroup), nullable=False)
    pre_test_score = Column(Float, nullable=True)
    post_test_score = Column(Float, nullable=True)
    # #9 study-buddy: a short shareable code so two users can see each other's
    # privacy-safe forecast without any account system. Nullable for users that
    # predate this column; generated lazily via the API when missing.
    share_code = Column(String(12), unique=True, index=True, nullable=True)

    sessions = relationship("StudySession", back_populates="user")
    retention_checks = relationship("RetentionCheck", back_populates="user")
    fingerprint = relationship("CognitiveFingerprint", back_populates="user", uselist=False)


class Material(Base):
    __tablename__ = "materials"

    id = Column(Integer, primary_key=True, index=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    title = Column(String(255), nullable=False)
    raw_text = Column(Text, nullable=False)
    knowledge_map_json = Column(Text, nullable=True)
    questions_json = Column(Text, nullable=True)  # cached LLM-generated flashcards

    sessions = relationship("StudySession", back_populates="material")


class StudySession(Base):
    __tablename__ = "study_sessions"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    material_id = Column(Integer, ForeignKey("materials.id"), nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)
    technique = Column(Enum(StudyTechnique), nullable=False)
    duration_minutes = Column(Integer, nullable=False)
    time_of_day = Column(Enum(TimeOfDay), nullable=False)
    sleep_hours = Column(Float, nullable=True)
    stress_level = Column(Integer, nullable=True)  # 1–5
    quiz_score = Column(Float, nullable=False)  # 0.0–1.0 (immediate)

    user = relationship("User", back_populates="sessions")
    material = relationship("Material", back_populates="sessions")
    retention_checks = relationship("RetentionCheck", back_populates="session")


class RetentionCheck(Base):
    __tablename__ = "retention_checks"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(Integer, ForeignKey("study_sessions.id"), nullable=False)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    checked_at = Column(DateTime, default=utcnow, nullable=False)
    check_type = Column(String(10), nullable=False)  # "24h" or "7d"
    score = Column(Float, nullable=False)  # 0.0–1.0

    session = relationship("StudySession", back_populates="retention_checks")
    user = relationship("User", back_populates="retention_checks")


class CognitiveFingerprint(Base):
    __tablename__ = "cognitive_fingerprints"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), unique=True, nullable=False)
    updated_at = Column(DateTime, default=utcnow, onupdate=utcnow, nullable=False)
    session_count = Column(Integer, default=0, nullable=False)
    profile_json = Column(Text, nullable=True)      # serialized FingerprintProfile
    bandit_state_json = Column(Text, nullable=True)  # serialized LinUCBRecommender

    # Observability (§4.2): the rebuild runs as a fire-and-forget background task;
    # without this, a failed rebuild silently leaves a stale profile with no signal.
    # "ok" | "failed" | "pending" (None on rows that predate this column).
    last_rebuild_status = Column(String(16), nullable=True)
    last_rebuild_at = Column(DateTime, nullable=True)
    last_rebuild_error = Column(Text, nullable=True)  # truncated message, ops-only

    user = relationship("User", back_populates="fingerprint")


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    Base.metadata.create_all(bind=engine)
    _migrate_add_missing_columns()


def _migrate_add_missing_columns():
    """Pragmatic pre-Alembic migration: `create_all` never ALTERs existing
    tables, so a DB created before a column was added silently breaks every
    query touching the model. Until Postgres+Alembic land (§4.2), add any
    missing declared columns with ADD COLUMN (nullable ⇒ safe + idempotent)."""
    from sqlalchemy import inspect as sa_inspect, text

    inspector = sa_inspect(engine)
    with engine.begin() as conn:
        for table in Base.metadata.sorted_tables:
            if not inspector.has_table(table.name):
                continue
            existing = {c["name"] for c in inspector.get_columns(table.name)}
            for col in table.columns:
                if col.name in existing or not col.nullable:
                    continue  # non-nullable additions need a real migration
                coltype = col.type.compile(engine.dialect)
                conn.execute(text(
                    f'ALTER TABLE {table.name} ADD COLUMN "{col.name}" {coltype}'
                ))
