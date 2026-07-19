from datetime import datetime
from typing import Dict, List, Optional

from pydantic import BaseModel, Field, field_validator

from config import CHECK_TYPE_KEYS
from database import StudyGroup, StudyTechnique, TimeOfDay
from schemas.fingerprint import FingerprintProfile


# --- Request models ---

class UserCreate(BaseModel):
    group: StudyGroup
    pre_test_score: Optional[float] = Field(None, ge=0.0, le=1.0)


class SessionCreate(BaseModel):
    user_id: int
    material_id: Optional[int] = None
    technique: StudyTechnique
    duration_minutes: int = Field(gt=0, le=480)
    time_of_day: TimeOfDay
    sleep_hours: Optional[float] = Field(None, ge=0.0, le=24.0)
    stress_level: Optional[int] = Field(None, ge=1, le=5)
    quiz_score: float = Field(ge=0.0, le=1.0)


class RetentionCheckCreate(BaseModel):
    session_id: int
    user_id: int
    check_type: str  # one of config.CHECK_TYPE_KEYS (currently "24h" / "7d")
    score: float = Field(ge=0.0, le=1.0)

    @field_validator("check_type")
    @classmethod
    def validate_check_type(cls, v: str) -> str:
        if v not in CHECK_TYPE_KEYS:
            raise ValueError(f"check_type must be one of {CHECK_TYPE_KEYS}")
        return v


class MaterialCreate(BaseModel):
    title: str
    raw_text: str


class OcrRequest(BaseModel):
    """A photo of notes/textbook to transcribe (base64, no data-URL prefix)."""

    image_base64: str
    media_type: str  # one of agents.material_ocr.ALLOWED_MEDIA_TYPES


class OcrResponse(BaseModel):
    text: str


class PostTestUpdate(BaseModel):
    post_test_score: float = Field(ge=0.0, le=1.0)


# --- Response models ---

class UserResponse(BaseModel):
    id: int
    group: StudyGroup
    pre_test_score: Optional[float]
    post_test_score: Optional[float]
    created_at: datetime

    model_config = {"from_attributes": True}


class SessionResponse(BaseModel):
    id: int
    user_id: int
    material_id: Optional[int]
    technique: StudyTechnique
    duration_minutes: int
    time_of_day: TimeOfDay
    sleep_hours: Optional[float]
    stress_level: Optional[int]
    quiz_score: float
    created_at: datetime

    model_config = {"from_attributes": True}


class RetentionCheckResponse(BaseModel):
    id: int
    session_id: int
    user_id: int
    check_type: str
    score: float
    checked_at: datetime

    model_config = {"from_attributes": True}


class MaterialResponse(BaseModel):
    id: int
    title: str
    knowledge_map_json: Optional[str]
    created_at: datetime

    model_config = {"from_attributes": True}


class FingerprintResponse(BaseModel):
    user_id: int
    fingerprint: FingerprintProfile
    updated_at: datetime
    # Observability (§4.2): surfaces whether the last background rebuild succeeded
    # so a silently-stale fingerprint is detectable. None until the first rebuild.
    rebuild_status: Optional[str] = None      # "ok" | "failed" | "pending"
    rebuild_at: Optional[datetime] = None


class StudyPlanDay(BaseModel):
    day: int
    technique: str
    topic_focus: str
    session_duration_minutes: int
    time_of_day: str
    rationale: str


class MaterialProfile(BaseModel):
    """Aggregate cognitive shape of the material itself, independent of any
    learner. Drives material-aware technique matching: some techniques fit
    factual/foundational text, others fit abstract/advanced text (Dunlosky
    et al. 2013). Combined with the fingerprint to pick a technique per concept."""

    dominant_type: str                 # factual | conceptual | procedural
    dominant_difficulty: str           # foundational | intermediate | advanced
    type_mix: Dict[str, float]         # normalised proportions, sums to ~1
    difficulty_mix: Dict[str, float]   # normalised proportions, sums to ~1
    summary: str                       # one human-readable sentence


class StudyPlanResponse(BaseModel):
    user_id: int
    total_days: int
    days: List[StudyPlanDay]
    general_advice: str
    # Optional so existing callers/clients are unaffected (older frontends just
    # ignore it). Populated by the planner for material-aware surfacing.
    material_profile: Optional[MaterialProfile] = None


class KnowledgeConcept(BaseModel):
    concept: str
    difficulty: str  # "foundational", "intermediate", "advanced"
    concept_type: str  # "factual", "conceptual", "procedural"
    related_concepts: List[str] = Field(default_factory=list)


class KnowledgeMap(BaseModel):
    title: str
    total_concepts: int
    concepts: List[KnowledgeConcept]
    suggested_study_order: List[str]


class MaterialAnalysisResponse(BaseModel):
    material_id: int
    knowledge_map: KnowledgeMap


# --- Review suggestions (predicted forgetting) ---

class ReviewSuggestion(BaseModel):
    """One material's predicted-forgetting state, for the 'about to forget X'
    nudge. Sorted ascending by predicted_retention by the endpoint."""

    material_id: int
    title: str
    last_studied: datetime
    days_since: float
    predicted_retention: float  # R(t) = exp(-t/S), 0..1
    fading: bool                # predicted_retention < FADING_THRESHOLD


# --- Material library (§3.3) ---

class MaterialLibraryItem(BaseModel):
    """One material in a user's library — everything the returning-user home
    needs to browse, resume, and prioritise decks. Derived from the user's own
    sessions (materials aren't user-owned in the schema; the link is the
    sessions), enriched with the same Ebbinghaus forgetting state as the
    review-suggestions nudge so 'what needs review' is consistent across the app."""

    material_id: int
    title: str
    created_at: datetime
    last_studied: datetime
    session_count: int
    concept_count: int
    predicted_retention: float  # R(t) = exp(-t/S), 0..1 (most-recent technique)
    fading: bool                # predicted_retention < FADING_THRESHOLD
    reviews_due: int            # pending 24h/7d checks across this material's sessions


# --- Research export ---

class ResearchExportRow(BaseModel):
    user_id: int
    group: str
    session_id: int
    session_date: datetime
    technique: str
    duration_minutes: int
    time_of_day: str
    sleep_hours: Optional[float]
    stress_level: Optional[int]
    quiz_score: float
    retention_24h: Optional[float]
    retention_7d: Optional[float]
    pre_test_score: Optional[float]
    post_test_score: Optional[float]
