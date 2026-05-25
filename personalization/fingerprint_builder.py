import json
from datetime import datetime

from sqlalchemy.orm import Session

from database import CognitiveFingerprint, RetentionCheck, StudySession, User
from schemas.fingerprint import ConfidenceLevel, FingerprintProfile, TechniqueMemoryProfile
from personalization.serializer import serialize_for_agent2


def _confidence_from_count(n: int) -> ConfidenceLevel:
    if n < 5:
        return ConfidenceLevel.LOW
    if n < 16:
        return ConfidenceLevel.MEDIUM
    return ConfidenceLevel.HIGH


def get_or_create_fingerprint(db: Session, user_id: int) -> CognitiveFingerprint:
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    if not fp:
        fp = CognitiveFingerprint(user_id=user_id, session_count=0, profile_json=None)
        db.add(fp)
        db.commit()
        db.refresh(fp)
    return fp


def load_profile(fp: CognitiveFingerprint) -> FingerprintProfile:
    if fp.profile_json:
        return FingerprintProfile.model_validate_json(fp.profile_json)
    return FingerprintProfile(session_count=fp.session_count)


def rebuild_fingerprint(db: Session, user_id: int) -> FingerprintProfile:
    """
    Re-computes the cognitive fingerprint for a user from all their sessions.
    Delegates synthesis to Agent 2 (PerformanceOptimizer) for users with enough data.
    For the control group (or users with < 5 sessions), returns a minimal generic profile.
    """
    from agents.performance_optimizer import PerformanceOptimizer

    user: User = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise ValueError(f"User {user_id} not found")

    sessions: list[StudySession] = (
        db.query(StudySession)
        .filter_by(user_id=user_id)
        .order_by(StudySession.created_at)
        .all()
    )
    session_ids = [s.id for s in sessions]
    retention_checks: list[RetentionCheck] = (
        db.query(RetentionCheck)
        .filter(RetentionCheck.session_id.in_(session_ids))
        .all()
        if session_ids else []
    )

    n = len(sessions)

    # Control group: collect data but return generic profile (no personalization shown)
    from database import StudyGroup
    if user.group == StudyGroup.CONTROL:
        profile = FingerprintProfile(
            session_count=n,
            confidence=ConfidenceLevel.LOW,
            insights=["Keep up your regular study routine."],
            data_gaps=["Personalization not enabled for this study group."],
        )
        memory_profiles: dict = {}
    else:
        user_context, memory_profiles = serialize_for_agent2(sessions, retention_checks)
        optimizer = PerformanceOptimizer()
        profile = optimizer.build_fingerprint(user_context, n)

    # Embed forgetting-curve fits directly — these are computed from data,
    # not LLM-generated, so they are always authoritative regardless of study group.
    profile.memory_profiles = [
        TechniqueMemoryProfile(**mp) for mp in memory_profiles.values()
    ]

    # Persist
    fp = get_or_create_fingerprint(db, user_id)
    fp.session_count = n
    fp.profile_json = profile.model_dump_json()
    fp.updated_at = datetime.utcnow()
    db.commit()
    db.refresh(fp)

    return profile
