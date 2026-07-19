import csv
import io
import json
import logging
import os
from datetime import datetime, timedelta
from typing import List, Optional

from fastapi import BackgroundTasks, Depends, FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from pydantic import BaseModel
from sqlalchemy.orm import Session

from auth import require_api_key
from config import RETENTION_SCHEDULE
from schemas.question import FlagQuestionRequest, QuestionSetResponse
from database import (
    CognitiveFingerprint,
    Material,
    RetentionCheck,
    SessionLocal,
    StudyGroup,
    StudySession,
    User,
    generate_share_code,
    get_db,
    init_db,
    utcnow,
)
from personalization.fingerprint_builder import load_profile, rebuild_fingerprint
from schemas.fingerprint import ConfidenceLevel, FingerprintProfile
from schemas.session import (
    FingerprintResponse,
    MaterialAnalysisResponse,
    MaterialCreate,
    MaterialLibraryItem,
    OcrRequest,
    OcrResponse,
    PostTestUpdate,
    RetentionCheckCreate,
    RetentionCheckResponse,
    ResearchExportRow,
    ReviewSuggestion,
    SessionCreate,
    SessionResponse,
    StudyPlanResponse,
    UserCreate,
    UserResponse,
)

logger = logging.getLogger("cogprint")

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


def _record_rebuild_status(
    db: Session, user_id: int, status: str, error: Optional[str] = None
) -> None:
    """Stamp the outcome of a rebuild onto the user's fingerprint row so a failed
    rebuild is observable (§4.2) instead of silently leaving a stale profile.
    Creates a placeholder row if the rebuild failed before one existed."""
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    if fp is None:
        fp = CognitiveFingerprint(user_id=user_id, session_count=0)
        db.add(fp)
    fp.last_rebuild_status = status
    fp.last_rebuild_at = utcnow()
    fp.last_rebuild_error = (error or None) and error[:500]
    db.commit()


def _rebuild_fingerprint_bg(user_id: int) -> None:
    """Rebuild a user's fingerprint in a background task.

    Runs *after* the HTTP response is sent, so logging a session/retention
    check returns immediately instead of blocking on the full MCMC pipeline.
    The request-scoped DB session is already closed by the time this fires,
    so we open our own and always close it.

    A failed rebuild must never surface as a failed data-logging request — but
    it must not vanish either. On failure we log it and stamp last_rebuild_status
    on the fingerprint row so the staleness is visible to the user and to ops.
    """
    db = SessionLocal()
    try:
        rebuild_fingerprint(db, user_id)
        _record_rebuild_status(db, user_id, "ok")
    except Exception as e:  # noqa: BLE001 — must not propagate to the request
        logger.exception("fingerprint rebuild failed for user %s", user_id)
        try:
            db.rollback()
            _record_rebuild_status(db, user_id, "failed", repr(e))
        except Exception:  # noqa: BLE001 — status write is best-effort
            logger.exception("failed to record rebuild status for user %s", user_id)
    finally:
        db.close()


# ---------------------------------------------------------------------------
# Users
# ---------------------------------------------------------------------------

def _fresh_share_code(db: Session) -> str:
    """A share code guaranteed unique in the users table."""
    for _ in range(10):
        code = generate_share_code()
        if not db.query(User).filter_by(share_code=code).first():
            return code
    # Astronomically unlikely after 10 tries; widen the code as a fallback.
    return generate_share_code(10)


@app.post("/users", response_model=UserResponse, status_code=201)
def create_user(body: UserCreate, db: Session = Depends(get_db)):
    user = User(
        group=body.group,
        pre_test_score=body.pre_test_score,
        share_code=_fresh_share_code(db),
    )
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
        # No usable profile yet — return a generic empty fingerprint, but still
        # surface rebuild status so a failed first rebuild (row exists, no
        # profile) is detectable rather than looking like "no data yet".
        profile = FingerprintProfile(
            session_count=0,
            confidence=ConfidenceLevel.LOW,
            data_gaps=["No sessions recorded yet."],
        )
        return FingerprintResponse(
            user_id=user_id,
            fingerprint=profile,
            updated_at=utcnow(),
            rebuild_status=fp.last_rebuild_status if fp else None,
            rebuild_at=fp.last_rebuild_at if fp else None,
        )

    return FingerprintResponse(
        user_id=user_id,
        fingerprint=load_profile(fp),
        updated_at=fp.updated_at,
        rebuild_status=fp.last_rebuild_status,
        rebuild_at=fp.last_rebuild_at,
    )


@app.post("/users/{user_id}/fingerprint/rebuild", response_model=FingerprintResponse)
def force_rebuild_fingerprint(user_id: int, db: Session = Depends(get_db)):
    """Manually trigger a fingerprint rebuild ("rebuild now", §4.2) — useful after
    bulk import or to recover from a failed background rebuild. Unlike the
    background path this runs synchronously so the caller sees the outcome; a
    genuine failure surfaces as a 500 (and is stamped on the row)."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    try:
        profile = rebuild_fingerprint(db, user_id)
        _record_rebuild_status(db, user_id, "ok")
    except Exception as e:  # noqa: BLE001
        logger.exception("manual fingerprint rebuild failed for user %s", user_id)
        db.rollback()
        _record_rebuild_status(db, user_id, "failed", repr(e))
        raise HTTPException(status_code=500, detail="Rebuild failed; status recorded.")

    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    return FingerprintResponse(
        user_id=user_id,
        fingerprint=profile,
        updated_at=fp.updated_at if fp else utcnow(),
        rebuild_status=fp.last_rebuild_status if fp else "ok",
        rebuild_at=fp.last_rebuild_at if fp else utcnow(),
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
# Material OCR — photo of notes/textbook -> text (LLM vision, isolated)
# ---------------------------------------------------------------------------

# ~5 MB of decoded image; base64 inflates by 4/3. Module-level so tests can
# monkeypatch it instead of constructing a multi-MB payload.
MAX_OCR_B64_CHARS = 7_000_000


@app.post("/materials/ocr", response_model=OcrResponse)
def ocr_material(body: OcrRequest):
    """Transcribe a photo of study material into text.

    Pure text acquisition: does NOT create a Material — the frontend feeds the
    returned text into POST /materials/analyze, reusing the whole downstream
    pipeline unchanged. 503 (not 500) when the LLM isn't configured.
    """
    from agents.material_ocr import (
        ALLOWED_MEDIA_TYPES,
        OcrUnavailable,
        extract_text_from_image,
    )

    if body.media_type not in ALLOWED_MEDIA_TYPES:
        raise HTTPException(
            status_code=400,
            detail=f"media_type must be one of {sorted(ALLOWED_MEDIA_TYPES)}",
        )
    if len(body.image_base64) > MAX_OCR_B64_CHARS:
        raise HTTPException(status_code=413, detail="Image too large (max ~5 MB).")

    try:
        text = extract_text_from_image(body.image_base64, body.media_type)
    except OcrUnavailable as e:
        raise HTTPException(status_code=503, detail=str(e))

    return OcrResponse(text=text)


# ---------------------------------------------------------------------------
# Flashcard / question generation (Agent 4 — the only LLM-backed endpoint)
# ---------------------------------------------------------------------------

def _cards_out(stored: "StoredQuestions", include_flagged: bool) -> list:
    """Build response cards with stable ids + flag state, optionally hiding flagged."""
    from schemas.question import FlashcardOut

    flagged_set = set(stored.flagged)
    out = []
    for i, card in enumerate(stored.cards):
        is_flagged = i in flagged_set
        if is_flagged and not include_flagged:
            continue  # flagged cards are excluded from the study set by default
        out.append(FlashcardOut(id=i, flagged=is_flagged, **card.model_dump()))
    return out


@app.post("/materials/{material_id}/questions", response_model=QuestionSetResponse)
def generate_questions(
    material_id: int,
    n: int = 8,
    refresh: bool = False,
    include_flagged: bool = False,
    db: Session = Depends(get_db),
):
    """Generate (and cache) flashcards for a material via the LLM service.

    Cached on the material after first generation; pass ?refresh=true to force
    regeneration. Flagged ("bad/confusing") cards are excluded by default; pass
    ?include_flagged=true to see them. Returns 503 (not 500) when the LLM isn't
    configured, so the UI can show a clean 'add an API key to enable flashcards'
    state.
    """
    from agents.question_generator import (
        QuestionGenUnavailable,
        generate_flashcards,
    )
    from schemas.question import StoredQuestions

    material = db.query(Material).filter_by(id=material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")

    # Serve cached cards unless a refresh is requested. StoredQuestions tolerates
    # the older {cards:[...]} cache shape (flagged defaults to []).
    if material.questions_json and not refresh:
        stored = StoredQuestions.model_validate_json(material.questions_json)
        return QuestionSetResponse(
            material_id=material.id,
            title=material.title,
            cards=_cards_out(stored, include_flagged),
            generated_by="cache",
        )

    # LLM cards when a key is configured (premium); otherwise fall back to the
    # zero-LLM cloze generator (§2.4) so flashcards ALWAYS work — no dead 503,
    # no cost, offline. COGPRINT_MODE=free forces the local path even with a key.
    mode = os.getenv("COGPRINT_MODE", "hybrid").lower()
    used_llm = False
    if mode != "free":
        try:
            generated = generate_flashcards(material.title, material.raw_text, n=n)
            used_llm = True
        except QuestionGenUnavailable:
            generated = None
    else:
        generated = None

    if generated is None:
        from agents.question_generator_local import (
            generate_flashcards as generate_flashcards_local,
        )
        generated = generate_flashcards_local(material.title, material.raw_text, n=n)

    stored = StoredQuestions(cards=generated.cards, flagged=[])
    material.questions_json = stored.model_dump_json()
    db.commit()

    if used_llm:
        generated_by = f"llm:{os.getenv('COGPRINT_QGEN_MODEL', 'claude-opus-4-8')}"
    else:
        generated_by = "local:cloze"
    return QuestionSetResponse(
        material_id=material.id,
        title=material.title,
        cards=_cards_out(stored, include_flagged),
        generated_by=generated_by,
    )


@app.post("/materials/{material_id}/questions/flag", status_code=200)
def flag_question(material_id: int, body: FlagQuestionRequest, db: Session = Depends(get_db)):
    """Mark a flashcard as bad/confusing so it's excluded from study + modelling.

    `card_id` is the stable index of the card in the material's question set.
    Idempotent: flagging an already-flagged card is a no-op.
    """
    from schemas.question import StoredQuestions

    material = db.query(Material).filter_by(id=material_id).first()
    if not material:
        raise HTTPException(status_code=404, detail="Material not found")
    if not material.questions_json:
        raise HTTPException(status_code=404, detail="No questions generated for this material yet")

    stored = StoredQuestions.model_validate_json(material.questions_json)
    if body.card_id >= len(stored.cards):
        raise HTTPException(status_code=404, detail="card_id out of range")

    if body.card_id not in stored.flagged:
        stored.flagged.append(body.card_id)
        material.questions_json = stored.model_dump_json()
        db.commit()

    return {"material_id": material_id, "card_id": body.card_id,
            "flagged_count": len(stored.flagged)}


# ---------------------------------------------------------------------------
# Study plan generation (Agent 3)
# ---------------------------------------------------------------------------

@app.post("/users/{user_id}/study-plan", response_model=StudyPlanResponse)
def generate_study_plan(
    user_id: int,
    material_id: int,
    total_days: int = 14,
    target_date: Optional[str] = None,
    db: Session = Depends(get_db),
):
    """Generate (or re-generate) a study plan for a material.

    Adaptive (§3.3): if the user has studied this material before, the plan
    resumes from today (concepts treated as decayed reviews) instead of
    restarting. Pass ?target_date=YYYY-MM-DD (e.g. an exam date) to size the
    horizon instead of the default 14 days.
    """
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

    # Horizon from an exam date, if given (clamped to a sane 1..90 days).
    if target_date:
        try:
            exam = datetime.fromisoformat(target_date).date()
        except ValueError:
            raise HTTPException(status_code=422, detail="target_date must be ISO YYYY-MM-DD")
        total_days = max(1, min(90, (exam - utcnow().date()).days))

    # Adaptive resume state: prior sessions on THIS material and recency.
    material_sessions = (
        db.query(StudySession)
        .filter(StudySession.user_id == user_id, StudySession.material_id == material_id)
        .all()
    )
    prior_sessions = len(material_sessions)
    days_since_last_study: Optional[float] = None
    if material_sessions:
        last = max(s.created_at for s in material_sessions)
        days_since_last_study = max(0.0, (utcnow() - last).total_seconds() / 86400.0)

    knowledge_map = KnowledgeMap.model_validate_json(material.knowledge_map_json)

    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    fingerprint = load_profile(fp) if fp and fp.profile_json else FingerprintProfile(session_count=0)

    planner = StudyPlanner()
    return planner.generate_plan(
        user_id, knowledge_map, fingerprint, total_days,
        days_since_last_study=days_since_last_study,
        prior_sessions=prior_sessions,
    )


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
    filename = f"cogprint_export_{utcnow().strftime('%Y%m%d_%H%M%S')}.csv"
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
# Review suggestions — predicted forgetting per material (deterministic)
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/review-suggestions", response_model=List[ReviewSuggestion])
def get_review_suggestions(user_id: int, db: Session = Depends(get_db)):
    """Per-material predicted retention via Ebbinghaus R(t)=exp(-t/S).

    S is the user's own measured stability for the technique they last used on
    that material (from their fingerprint's memory_profiles) when available,
    else the population default. Control users' generic profiles carry no
    memory_profiles, so they get the default automatically — blinding intact.
    Sorted ascending by predicted retention (most-fading first).
    """
    from personalization.review import (
        DEFAULT_STABILITY_DAYS,
        FADING_THRESHOLD,
        predicted_retention,
    )

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = (
        db.query(StudySession)
        .filter(StudySession.user_id == user_id, StudySession.material_id.isnot(None))
        .all()
    )
    if not sessions:
        return []

    # Most recent session per material.
    latest: dict[int, StudySession] = {}
    for s in sessions:
        prev = latest.get(s.material_id)
        if prev is None or s.created_at > prev.created_at:
            latest[s.material_id] = s

    # Personalised stability by technique, from the user's own fingerprint.
    stability_by_tech: dict[str, float] = {}
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    if fp and fp.profile_json:
        profile = load_profile(fp)
        for m in profile.memory_profiles:
            stability_by_tech[m.technique] = m.avg_stability_days

    now = datetime.utcnow()
    items: list[ReviewSuggestion] = []
    for material_id, s in latest.items():
        material = db.query(Material).filter_by(id=material_id).first()
        if not material:
            continue
        days = max(0.0, (now - s.created_at).total_seconds() / 86400.0)
        technique = s.technique.value if hasattr(s.technique, "value") else str(s.technique)
        stability = stability_by_tech.get(technique, DEFAULT_STABILITY_DAYS)
        r = predicted_retention(days, stability)
        items.append(ReviewSuggestion(
            material_id=material_id,
            title=material.title,
            last_studied=s.created_at,
            days_since=round(days, 2),
            predicted_retention=round(r, 4),
            fading=r < FADING_THRESHOLD,
        ))

    items.sort(key=lambda x: x.predicted_retention)
    return items


# ---------------------------------------------------------------------------
# Material library (§3.3) — the returning-user home
# ---------------------------------------------------------------------------

@app.get("/users/{user_id}/materials", response_model=List[MaterialLibraryItem])
def get_material_library(user_id: int, db: Session = Depends(get_db)):
    """Every material this user has studied, newest-studied first, each with its
    concept count, how many times it's been studied, its Ebbinghaus forgetting
    state, and how many retention checks are due.

    Materials aren't user-owned in the schema, so the library is derived from the
    user's own sessions (the durable server-side signal). This is the backend
    home screen the localStorage 'recents' can't be: cross-device and review-aware.
    """
    from personalization.review import (
        DEFAULT_STABILITY_DAYS,
        FADING_THRESHOLD,
        predicted_retention,
    )

    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    sessions = (
        db.query(StudySession)
        .filter(StudySession.user_id == user_id, StudySession.material_id.isnot(None))
        .all()
    )
    if not sessions:
        return []

    # Personalised stability by technique from the user's own fingerprint.
    stability_by_tech: dict[str, float] = {}
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user_id).first()
    if fp and fp.profile_json:
        for m in load_profile(fp).memory_profiles:
            stability_by_tech[m.technique] = m.avg_stability_days

    # Pending-check lookup: which (session_id, check_type) are already done.
    session_ids = [s.id for s in sessions]
    done_checks: set[tuple[int, str]] = set()
    for rc in db.query(RetentionCheck).filter(RetentionCheck.session_id.in_(session_ids)).all():
        done_checks.add((rc.session_id, rc.check_type))

    now = utcnow()

    # Aggregate per material.
    agg: dict[int, dict] = {}
    for s in sessions:
        a = agg.setdefault(s.material_id, {"count": 0, "latest": s, "reviews_due": 0})
        a["count"] += 1
        if s.created_at > a["latest"].created_at:
            a["latest"] = s
        for cp in RETENTION_SCHEDULE:
            due = s.created_at + cp.delay
            if now >= due and (s.id, cp.key) not in done_checks:
                a["reviews_due"] += 1

    items: list[MaterialLibraryItem] = []
    for material_id, a in agg.items():
        material = db.query(Material).filter_by(id=material_id).first()
        if not material:
            continue
        latest = a["latest"]
        days = max(0.0, (now - latest.created_at).total_seconds() / 86400.0)
        technique = latest.technique.value if hasattr(latest.technique, "value") else str(latest.technique)
        stability = stability_by_tech.get(technique, DEFAULT_STABILITY_DAYS)
        r = predicted_retention(days, stability)

        concept_count = 0
        if material.knowledge_map_json:
            try:
                concept_count = int(json.loads(material.knowledge_map_json).get("total_concepts", 0))
            except (ValueError, TypeError):
                concept_count = 0

        items.append(MaterialLibraryItem(
            material_id=material_id,
            title=material.title,
            created_at=material.created_at,
            last_studied=latest.created_at,
            session_count=a["count"],
            concept_count=concept_count,
            predicted_retention=round(r, 4),
            fading=r < FADING_THRESHOLD,
            reviews_due=a["reviews_due"],
        ))

    items.sort(key=lambda x: x.last_studied, reverse=True)
    return items


# ---------------------------------------------------------------------------
# Pending retention checks
# ---------------------------------------------------------------------------

class PendingCheckItem(BaseModel):
    session_id: int
    check_type: str       # one of config.CHECK_TYPE_KEYS
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

    now = utcnow()
    pending: list[PendingCheckItem] = []
    # Iterate the locked schedule (config.RETENTION_SCHEDULE) so adding or moving
    # a checkpoint is a single edit in config.py, not scattered branches here.
    for s in sessions:
        for cp in RETENTION_SCHEDULE:
            due = s.created_at + cp.delay
            if now >= due and (s.id, cp.key) not in done_checks:
                pending.append(PendingCheckItem(
                    session_id=s.id, check_type=cp.key,
                    session_date=s.created_at, due_date=due,
                ))

    return pending


# ---------------------------------------------------------------------------
# #9 Study-buddy — privacy-safe forecast sharing via a short code.
#
# The ONLY thing a buddy can see is the aggregate forecast below: confidence,
# session count, and how many concepts are fading/cooling/solid. Never raw
# sessions, material content, scores, or the full fingerprint.
# ---------------------------------------------------------------------------

class BuddyForecast(BaseModel):
    share_code: str
    confidence: str
    session_count: int
    fading: int
    cooling: int
    solid: int
    reviews_due: int


class ShareCodeResponse(BaseModel):
    user_id: int
    share_code: str


def _reviews_due_count(db: Session, user_id: int) -> int:
    """How many retention checks are currently due (mirrors get_pending_checks)."""
    sessions = db.query(StudySession).filter_by(user_id=user_id).all()
    session_ids = [s.id for s in sessions]
    done: set[tuple[int, str]] = set()
    if session_ids:
        for rc in db.query(RetentionCheck).filter(
            RetentionCheck.session_id.in_(session_ids)
        ).all():
            done.add((rc.session_id, rc.check_type))
    now = utcnow()
    count = 0
    for s in sessions:
        for cp in RETENTION_SCHEDULE:
            if now >= s.created_at + cp.delay and (s.id, cp.key) not in done:
                count += 1
    return count


def _buddy_forecast(db: Session, user: User) -> BuddyForecast:
    fp = db.query(CognitiveFingerprint).filter_by(user_id=user.id).first()
    fading = cooling = solid = 0
    confidence = "low"
    session_count = 0
    if fp and fp.profile_json:
        profile = load_profile(fp)
        confidence = profile.confidence.value if hasattr(profile.confidence, "value") else str(profile.confidence)
        session_count = profile.session_count
        # Same buckets as the frontend memory forecast (forecast.ts).
        for m in profile.memory_profiles:
            r = m.predicted_retention_7d
            if r < 0.5:
                fading += 1
            elif r < 0.8:
                cooling += 1
            else:
                solid += 1
    return BuddyForecast(
        share_code=user.share_code or "",
        confidence=confidence,
        session_count=session_count,
        fading=fading,
        cooling=cooling,
        solid=solid,
        reviews_due=_reviews_due_count(db, user.id),
    )


@app.post("/users/{user_id}/share-code", response_model=ShareCodeResponse)
def get_or_create_share_code(user_id: int, db: Session = Depends(get_db)):
    """Return this user's buddy code, generating one lazily if they predate it."""
    user = db.query(User).filter_by(id=user_id).first()
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    if not user.share_code:
        user.share_code = _fresh_share_code(db)
        db.commit()
        db.refresh(user)
    return ShareCodeResponse(user_id=user.id, share_code=user.share_code)


@app.get("/buddy/{share_code}/forecast", response_model=BuddyForecast)
def get_buddy_forecast(share_code: str, db: Session = Depends(get_db)):
    """A buddy's privacy-safe forecast summary. No content, sessions, or scores."""
    user = db.query(User).filter_by(share_code=share_code.upper()).first()
    if not user:
        raise HTTPException(status_code=404, detail="No buddy with that code")
    return _buddy_forecast(db, user)


# ---------------------------------------------------------------------------
# Health check
# ---------------------------------------------------------------------------

@app.get("/health")
def health():
    return {"status": "ok", "service": "CogPrint API"}
