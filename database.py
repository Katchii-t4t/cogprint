import enum
import hashlib
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


_RECOVERY_PREFIX = "cog_"


def generate_recovery_token() -> str:
    """A bearer secret that lets a user reclaim their account on a new device.

    Replaces the old "type your numeric CogPrint ID" restore, which was
    trivially enumerable (ids are sequential). 24 random bytes = 192 bits of
    entropy, so guessing is not a threat model. The ``cog_`` prefix makes the
    string recognisable to the user (and greppable if one ever leaks).
    """
    return _RECOVERY_PREFIX + secrets.token_urlsafe(24)


def generate_magic_link_token() -> str:
    """Single-use secret embedded in an emailed link.

    No ``cog_`` prefix: unlike the recovery token this is never shown to the
    user as something to keep, it only ever lives inside a URL.
    """
    return secrets.token_urlsafe(24)


def hash_recovery_token(token: str) -> str:
    """Hash a recovery token for storage — the plaintext is never persisted.

    SHA-256 (not bcrypt/argon2) is the right choice here: those exist to slow
    brute force against *low-entropy human-chosen passwords*. This token is 192
    bits of CSPRNG output, so there is nothing to brute-force, and a fast hash
    keeps lookup a single indexed equality check rather than a table scan of
    per-row salted comparisons.
    """
    return hashlib.sha256(token.encode("utf-8")).hexdigest()


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
    # SHA-256 of the account-recovery token. Indexed because recovery looks the
    # user up *by* this hash — the plaintext token is returned exactly once, at
    # account creation, and never stored. Nullable for users that predate the
    # column: they cannot recover (there is no safe way to mint a token from an
    # id without recreating the enumeration hole this replaced).
    recovery_token_hash = Column(String(64), unique=True, index=True, nullable=True)
    # Optional second way back in (see MagicLinkToken). Unverified addresses are
    # stored but never accepted for login, so claiming someone else's address
    # gains nothing until they prove they own it.
    email = Column(String(255), unique=True, index=True, nullable=True)
    email_verified_at = Column(DateTime, nullable=True)
    # Frequency cap for re-engagement mail, so a doubled cron can't spam anyone.
    last_reminder_sent_at = Column(DateTime, nullable=True)

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


class MagicLinkToken(Base):
    """A single-use, short-lived secret delivered by email.

    Two purposes share one table because the lifecycle is identical — issue,
    email, consume once, expire — and only the side effect on redemption
    differs: ``verify_email`` marks the address as proven, ``login`` simply
    identifies the account on a new device.

    Only the hash is stored, matching the recovery-token design: a database
    leak must not hand out working links.
    """

    __tablename__ = "magic_link_tokens"

    id = Column(Integer, primary_key=True, index=True)
    user_id = Column(Integer, ForeignKey("users.id"), nullable=False)
    token_hash = Column(String(64), unique=True, index=True, nullable=False)
    purpose = Column(String(20), nullable=False)  # "verify_email" | "login"
    expires_at = Column(DateTime, nullable=False)
    consumed_at = Column(DateTime, nullable=True)
    created_at = Column(DateTime, default=utcnow, nullable=False)

    user = relationship("User")


class AnalyticsEvent(Base):
    """First-party product analytics.

    Deliberately not a third-party tool. The events needed to answer "does
    personalisation actually improve retention" are the study data itself, and
    shipping that to PostHog or Plausible would contradict the privacy posture
    that is part of this product's moat — as well as putting the research data
    somewhere it can't be joined against the rest of the schema.
    """

    __tablename__ = "analytics_events"

    id = Column(Integer, primary_key=True, index=True)
    # Nullable: the funnel starts before an account exists, and that leading
    # edge is exactly the population worth measuring.
    user_id = Column(Integer, ForeignKey("users.id"), nullable=True)
    event_name = Column(String(64), index=True, nullable=False)
    properties_json = Column(Text, nullable=True)
    created_at = Column(DateTime, default=utcnow, index=True, nullable=False)


def get_db():
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


def init_db():
    """Bring the database up to the current schema.

    Schema changes are Alembic migrations (``alembic upgrade head``); this only
    covers the two cases where that has not run yet:

      * a brand-new database — created from the models, then stamped at head so
        the next migration applies cleanly rather than trying to re-create
        tables that already exist;
      * an existing database created before Alembic was introduced — stamped at
        the baseline so its history starts from the right place.

    A database that is versioned but behind head is upgraded. Without that, a
    developer who pulls a schema change and starts the server gets a column-not-
    found crash at the first query instead of a migration — the failure this
    replaced an ADD COLUMN loop to avoid, arriving by a different route.
    """
    from sqlalchemy import inspect as sa_inspect

    if not sa_inspect(engine).has_table("users"):
        # Brand new: built straight from the models, so the schema really is
        # current and stamping head is the truth.
        Base.metadata.create_all(bind=engine)
        _stamp_alembic("head")
        return

    # Tables exist. Decide from the recorded revision rather than from the
    # presence of the version table, so a half-initialised database (table
    # present but empty) is handled the same as one that predates Alembic.
    if _current_revision() is None:
        # Predates Alembic. Stamping head would assert a currency it does not
        # have — the lie that leaves a column missing at the first query.
        # Stamping "base" would claim nothing is applied and then try to
        # re-create tables that exist. The truth is in between: its schema
        # matches the baseline revision, which was autogenerated from the
        # models at the moment Alembic was introduced.
        _stamp_alembic(_baseline_revision())

    _upgrade_if_behind()


def _baseline_revision() -> str:
    """The root of the migration history — the schema as it stood pre-Alembic."""
    from alembic.script import ScriptDirectory

    script = ScriptDirectory.from_config(_alembic_config())
    return list(script.walk_revisions())[-1].revision


def _current_revision():
    """The revision this database is stamped at, or None if never stamped."""
    from alembic.migration import MigrationContext

    with engine.connect() as conn:
        return MigrationContext.configure(conn).get_current_revision()


def _alembic_config():
    from alembic.config import Config

    root = os.path.dirname(os.path.abspath(__file__))
    cfg = Config(os.path.join(root, "alembic.ini"))
    cfg.set_main_option("script_location", os.path.join(root, "migrations"))
    return cfg


def _upgrade_if_behind():
    """Apply any pending migrations at startup.

    Idempotent and a no-op in production, where the container already runs
    ``alembic upgrade head`` before uvicorn (see Dockerfile) — this exists so a
    local checkout is never left half-migrated.

    Not a substitute for the deploy-time upgrade: several workers booting at
    once would race here, which is exactly why the Dockerfile migrates first,
    in one process, before any worker starts serving.
    """
    import logging

    try:
        from alembic import command
        from alembic.migration import MigrationContext
        from alembic.script import ScriptDirectory

        cfg = _alembic_config()
        script = ScriptDirectory.from_config(cfg)
        with engine.begin() as conn:
            current = MigrationContext.configure(conn).get_current_revision()
            if current == script.get_current_head():
                return
            cfg.attributes["connection"] = conn
            command.upgrade(cfg, "head")
    except Exception:
        logging.getLogger("cogprint").warning(
            "could not apply pending migrations; run 'alembic upgrade head'",
            exc_info=True,
        )


def _stamp_alembic(revision: str = "head"):
    """Record where in the migration history this schema already sits.

    The live connection is handed to Alembic so the stamp lands on the engine
    this process is actually using, rather than on whatever DATABASE_URL held
    when the module was imported.

    Best-effort: a missing or partial Alembic install must not stop the API
    booting. It is logged rather than swallowed, because the next
    ``alembic upgrade`` would otherwise behave unexpectedly.
    """
    import logging

    try:
        from alembic import command

        cfg = _alembic_config()
        with engine.begin() as conn:
            cfg.attributes["connection"] = conn
            command.stamp(cfg, revision)
    except Exception:
        logging.getLogger("cogprint").warning(
            "could not stamp the Alembic version table; run 'alembic stamp head' "
            "before the next migration", exc_info=True,
        )
