import csv
import io
import json
import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from sqlalchemy.orm import Session

from database import (
    CognitiveFingerprint,
    Material,
    RetentionCheck,
    SessionLocal,
    StudyGroup,
    StudySession,
    User,
    get_db,
    init_db,
)
from auth import require_api_key
from personalization.fingerprint_builder import load_profile, rebuild_fingerprint
from schemas.fingerprint import ConfidenceLevel, FingerprintProfile
from schemas.session import (
    FingerprintResponse,
    MaterialAnalysisResponse,
    MaterialCreate,
    PostTestUpdate,
    RetentionCheckCreate,
    RetentionCheckResponse,
    ResearchExportRow,
    SessionCreate,
    SessionResponse,
    StudyPlanResponse,
    UserCreate,
    UserResponse,
)

app = FastAPI(title="CogPrint API", version="0.1.0")

# CORS origins are configurable so the deployed research frontend can talk to the
# API without a code change. Set CORS_ORIGINS to a comma-separated list of URLs,
# e.g. CORS_ORIGINS="https://research.cogprint.app,http://localhost:5173".
# Defaults to the local Vite dev/preview ports for zero-config local development.
_default_origins = "http://localhost:5173,http://localhost:4173"
CORS_ORIGINS = [
    origin.strip()
    for origin in os.getenv("CORS_ORIGINS", _default_origins).split(",")
    if origin.strip()
]

app.add_middleware(
    CORSMiddleware,
    allow_origins=CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.on_event("startup")
def startup():
    init_db()


def _rebuild_fingerprint_bg(user_id: int) -> None:
    """Rebuild a user's fingerprint in a background task.

    Runs *after* the HTTP response is sent, so logging a session/retention
    check returns immediately instead of blocking on the full MCMC pipeline.
    The request-scoped DB session is already closed by the time this fires,
    so we open our own and always close it. Failures are swallowed: a failed
    rebuild must never surface as a failed data-logging request.
    """
    db = SessionLocal()
    try:
        rebuild_fingerprint(db, user_id)
    except Exception:
        pass
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    user = User(group=body.group, pre_test_score=body.pre_test_score)
    db.add(user)
    db.commit()
    db.refresh(user)
    return user


@app.get("/users/all", dependencies=[Depends(require_api_key)])
def list_all_users(db: Session = Depends(get_db)):
    """Return all users with their session counts — for the researcher dashboard.

    Protected by the optional API key (see auth.py): exposes every participant.
    """
    users = db.query(User).order_by(User.id).all()
    result = []
    for u in users:
        session_count = db.query(StudySession).filter_by(user_id=u.id).count()
        result.append({
            "id": u.id,
            "group": u.group.value,
            "pre_test_score": u.pre_test_score,
            "post_test_score": u.post_test_score,
            "created_at": u.created_at.isoformat(),
            "session_count": session_count,
        })
    return result


@app.get("/users/{user_id}", response_model=UserResponse)
def get_user(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    return user


@app.patch("/users/{user_id}/post-test", response_model=UserResponse)
def update_post_test(user_id: int, body: PostTestUpdate, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    user.post_test_score = body.post_test_score
    db.commit()
    db.refresh(user)
    return user


# ---------------------------------------------------------------------------
# Study sessions
# ---------------------------------------------------------------------------

@app.post("/sessions", response_model=SessionResponse, status_code=201)
def log_session(
    body: SessionCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    user = db.query(User).filter_by(id=body.user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    session = StudySession(
        user_id=body.user_id,
        material_id=body.material_id,
        technique=body.technique,
        duration_minutes=body.duration_minutes,
        time_of_day=body.time_of_day,
        sleep_hours=body.sleep_hours,
        stress_level=body.stress_level,
        quiz_score=body.quiz_score,
    )
    db.add(session)
    db.commit()
    db.refresh(session)

    # Rebuild the fingerprint after the response is sent so the participant's
    # "log session" request stays fast even as the MCMC pipeline grows.
    background_tasks.add_task(_rebuild_fingerprint_bg, body.user_id)

    return session


# ---------------------------------------------------------------------------
# Retention checks
# ---------------------------------------------------------------------------

@app.post("/retention-checks", response_model=RetentionCheckResponse, status_code=201)
def log_retention_check(
    body: RetentionCheckCreate,
    background_tasks: BackgroundTasks,
    db: Session = Depends(get_db),
):
    session = db.query(StudySession).filter_by(id=body.session_id).first()
    if not session or session.user_id != body.user_id:
        raise HTTPException(status_code=404, detail="Session not found for this user")

    existing = (
        db.query(RetentionCheck)
        .filter_by(session_id=body.session_id, check_type=body.check_type)
        .first()
    )
    if existing:
        raise HTTPException(
            status_code=409,
            detail=f"{body.check_type} retention check already logged for this session",
        )

    check = RetentionCheck(
        session_id=body.session_id,
        user_id=body.user_id,
        check_type=body.check_type,
        score=body.score,
    )
    db.add(check)
    db.commit()
    db.refresh(check)

    # Rebuild fingerprint in the background now that we have new retention data.
    background_tasks.add_task(_rebuild_fingerprint_bg, body.user_id)

    return check


# ---------------------------------------------------------------------------
# Cognitive fingerprint
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/fingerprint", response_model=FingerprintResponse)
def get_fingerprint(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()

    if not fp or not fp.profile_json:
        # No data yet — return a generic empty fingerprint
        profile = FingerprintProfile(
            session_count=0,
            confidence=ConfidenceLevel.LOW,
            data_gaps=["No sessions recorded yet."],
        )
        return FingerprintResponse(
            user_id=user_id,
            fingerprint=profile,
            updated_at=datetime.utcnow(),
        )

    return FingerprintResponse(
        user_id=user_id,
        fingerprint=load_profile(fp),
        updated_at=fp.updated_at,
    )


@app.post("/users/{user_id}/fingerprint/rebuild", response_model=FingerprintResponse)
def force_rebuild_fingerprint(user_id: int, db: Session = Depends(get_db)):
    """Manually trigger a fingerprint rebuild — useful after bulk data import."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    profile = rebuild_fingerprint(db, user_id)
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()

    return FingerprintResponse(
        user_id=user_id,
        fingerprint=profile,
        updated_at=fp.updated_at if fp else datetime.utcnow(),
    )


# ---------------------------------------------------------------------------
# Material analysis (Agent 1)
# ---------------------------------------------------------------------------

@app.post("/materials/analyze", response_model=MaterialAnalysisResponse, status_code=201)
def analyze_material(body: MaterialCreate, db: Session = Depends(get_db)):
    from agents.material_analyzer import MaterialAnalyzer

    material = Material(title=body.title, raw_text=body.raw_text)
    db.add(material)
    db.commit()
    db.refresh(material)

    analyzer = MaterialAnalyzer()
    knowledge_map = analyzer.analyze(body.title, body.raw_text)

    material.knowledge_map_json = knowledge_map.model_dump_json()
    db.commit()

    return MaterialAnalysisResponse(material_id=material.id, knowledge_map=knowledge_map)


# ---------------------------------------------------------------------------
# Study plan generation (Agent 3)
# ---------------------------------------------------------------------------

@app.post("/users/{user_id}/study-plan", response_model=StudyPlanResponse)
def generate_study_plan(
    user_id: int,
    material_id: int,
    total_days: int = 14,
    db: Session = Depends(get_db),
):
    from agents.study_planner import StudyPlanner
    from schemas.session import KnowledgeMap

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    material = db.query(Material).filter_by(id=material_id).first()
    if not material or not material.knowledge_map_json:
        raise HTTPException(
            status_code=404,
            detail="Material not found or not yet analyzed. POST /materials/analyze first.",
        )

    knowledge_map = KnowledgeMap.model_validate_json(material.knowledge_map_json)

    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    fingerprint = load_profile(fp) if fp and fp.profile_json else FingerprintProfile(session_count=0)

    planner = StudyPlanner()
    return planner.generate_plan(user_id, knowledge_map, fingerprint, total_days)


# ---------------------------------------------------------------------------
# Research data export (CSV)
# ---------------------------------------------------------------------------

@app.get("/export/study-data", dependencies=[Depends(require_api_key)])
def export_study_data(
    group: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """
    Export all session-level data as CSV for statistical analysis.
    Optionally filter by group: ?group=control or ?group=treatment
    Columns: user_id, group, session_id, session_date, technique, duration_minutes,
             time_of_day, sleep_hours, stress_level, quiz_score,
             retention_24h, retention_7d, pre_test_score, post_test_score
    """
    query = db.query(StudySession).join(User)
    if group:
        try:
            study_group = StudyGroup(group)
        except ValueError:
            raise HTTPException(status_code=400, detail="group must be 'control' or 'treatment'")
        query = query.filter(User.group == study_group)

    sessions: list[StudySession] = query.order_by(StudySession.user_id, StudySession.created_at).all()

    # Index retention checks by (session_id, check_type)
    all_session_ids = [s.id for s in sessions]
    retention_index: dict[tuple[int, str], float] = {}
    if all_session_ids:
        checks = (
            db.query(RetentionCheck)
            .filter(RetentionCheck.session_id.in_(all_session_ids))
            .all()
        )
        for rc in checks:
            retention_index[(rc.session_id, rc.check_type)] = rc.score

    output = io.StringIO()
    fieldnames = [
        "user_id", "group", "session_id", "session_date", "technique",
        "duration_minutes", "time_of_day", "sleep_hours", "stress_level",
        "quiz_score", "retention_24h", "retention_7d",
        "pre_test_score", "post_test_score",
    ]
    writer = csv.DictWriter(output, fieldnames=fieldnames)
    writer.writeheader()

    for s in sessions:
        user: User = s.user
        writer.writerow({
            "user_id": s.user_id,
            "group": user.group.value,
            "session_id": s.id,
            "session_date": s.created_at.isoformat(),
            "technique": s.technique.value,
            "duration_minutes": s.duration_minutes,
            "time_of_day": s.time_of_day.value,
            "sleep_hours": s.sleep_hours if s.sleep_hours is not None else "",
            "stress_level": s.stress_level if s.stress_level is not None else "",
            "quiz_score": s.quiz_score,
            "retention_24h": retention_index.get((s.id, "24h"), ""),
            "retention_7d": retention_index.get((s.id, "7d"), ""),
            "pre_test_score": user.pre_test_score if user.pre_test_score is not None else "",
            "post_test_score": user.post_test_score if user.post_test_score is not None else "",
        })

    output.seek(0)
    filename = f"cogprint_export_{datetime.utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
    return StreamingResponse(
        iter([output.getvalue()]),
        media_type="text/csv",
        headers={"Content-Disposition": f"attachment; filename={filename}"},
    )


# ---------------------------------------------------------------------------
# Session listing
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/sessions", response_model=List[SessionResponse])
def list_sessions(user_id: int, db: Session = Depends(get_db)):
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    sessions = (
        db.query(StudySession)
        .filter_by(user_id=user_id)
        .order_by(StudySession.created_at.desc())
        .all()
    )
    return sessions


# ---------------------------------------------------------------------------
# Pending retention checks
# ---------------------------------------------------------------------------

class PendingCheck(BaseModel if False else object):
    pass


from pydantic import BaseModel as _Base


class PendingCheckItem(_Base):
    session_id: int
    check_type: str       # "24h" or "7d"
    session_date: datetime
    due_date: datetime


@app.get("/users/{user_id}/pending-checks")
def get_pending_checks(user_id: int, db: Session = Depends(get_db)) -> List[PendingCheckItem]:
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = db.query(StudySession).filter_by(user_id=user_id).all()
    session_ids = [s.id for s in sessions]

    done_checks: set[tuple[int, str]] = set()
    if session_ids:
        for rc in db.query(RetentionCheck).filter(RetentionCheck.session_id.in_(session_ids)).all():
            done_checks.add((rc.session_id, rc.check_type))

    now = datetime.utcnow()
    pending: list[PendingCheckItem] = []
    for s in sessions:
        due_24h = s.created_at + timedelta(hours=24)
        due_7d = s.created_at + timedelta(days=7)
        if now >= due_24h and (s.id, "24h") not in done_checks:
            pending.append(PendingCheckItem(
                session_id=s.id, check_type="24h",
                session_date=s.created_at, due_date=due_24h,
            ))
        if now >= due_7d and (s.id, "7d") not in done_checks:
            pending.append(PendingCheckItem(
                session_id=s.id, check_type="7d",
                session_date=s.created_at, due_date=due_7d,
            ))

    return pending


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "CogPrint API"}
