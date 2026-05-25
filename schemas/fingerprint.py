from enum import Enum
from typing import List, Optional

from pydantic import BaseModel, ConfigDict, Field


class ConfidenceLevel(str, Enum):
    LOW = "low"      # < 5 sessions — generic guidance only
    MEDIUM = "medium"  # 5–15 sessions — moderate personalization
    HIGH = "high"    # 16+ sessions — strong personalization


class TechniqueMemoryProfile(BaseModel):
    """
    Per-technique Ebbinghaus forgetting-curve statistics.
    S (stability) is fitted from the user's own 24 h / 7 d retention checks.
    """
    model_config = ConfigDict(extra="forbid")

    technique: str
    avg_stability_days: float
    """Fitted Ebbinghaus S parameter (days). Higher = slower forgetting."""
    stability_label: str
    """Qualitative label: 'poor' | 'fair' | 'good' | 'excellent'."""
    predicted_retention_7d: float
    """Model-predicted retention after 7 days: R(7) = e^(−7/S)."""
    optimal_review_interval_days: int
    """Days until predicted retention drops to 85 % — ideal next-review window."""
    sessions_with_curve_data: int
    avg_7d_retention: Optional[float] = None
    """Raw 7-day retention average (no model, for cross-validation)."""


class TechniqueStats(BaseModel):
    model_config = ConfigDict(extra="forbid")

    technique: str
    sessions_observed: int
    avg_immediate_score: Optional[float] = None
    avg_retention_24h: Optional[float] = None
    avg_retention_7d: Optional[float] = None
    # "best", "good", "average", "poor" — set by Agent 2
    relative_effectiveness: Optional[str] = None


class OptimalConditions(BaseModel):
    model_config = ConfigDict(extra="forbid")

    best_time_of_day: Optional[str] = None
    optimal_session_duration_minutes: Optional[int] = None
    min_sleep_hours_recommended: Optional[float] = None
    max_stress_level_recommended: Optional[int] = None
    sleep_score_correlation: Optional[float] = None    # Pearson r (sleep_hours vs quiz_score)
    stress_score_correlation: Optional[float] = None   # Pearson r (stress_level vs quiz_score)
    duration_score_correlation: Optional[float] = None  # Pearson r (duration vs quiz_score)


class FingerprintProfile(BaseModel):
    model_config = ConfigDict(extra="forbid")

    session_count: int = 0
    confidence: ConfidenceLevel = ConfidenceLevel.LOW
    technique_effectiveness: List[TechniqueStats] = Field(default_factory=list)
    optimal_conditions: OptimalConditions = Field(default_factory=OptimalConditions)
    recommended_techniques: List[str] = Field(default_factory=list)
    recommended_session_duration_minutes: Optional[int] = None
    insights: List[str] = Field(default_factory=list)
    data_gaps: List[str] = Field(default_factory=list)
    improving_over_time: Optional[bool] = None
    avg_score_trend_per_week: Optional[float] = None
    memory_profiles: List[TechniqueMemoryProfile] = Field(
        default_factory=list,
        description="Per-technique Ebbinghaus forgetting-curve fits. "
                    "Populated directly from measured retention data — not LLM-generated.",
    )
