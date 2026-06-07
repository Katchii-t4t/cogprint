from datetime import datetime
from typing import List, Optional

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


class StudyPlanDay(BaseModel):
    day: int
    technique: str
    topic_focus: str
    session_duration_minutes: int
    time_of_day: str
    rationale: str


class StudyPlanResponse(BaseModel):
    user_id: int
    total_days: int
    days: List[StudyPlanDay]
    general_advice: str


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
