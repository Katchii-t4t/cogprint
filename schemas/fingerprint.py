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


class BayesianStabilityStats(BaseModel):
    """
    Per-technique posterior over the Ebbinghaus stability parameter S,
    computed by Metropolis-Hastings MCMC under the hierarchical population prior.
    """
    model_config = ConfigDict(extra="forbid")

    technique: str
    posterior_mean_days: float
    """E[S | data, population] — posterior mean stability in days."""
    posterior_median_days: float
    """Posterior median (more robust than mean for skewed log-normal posteriors)."""
    posterior_std_days: float
    """Posterior standard deviation — proxy for estimation uncertainty."""
    ci_lower_days: float
    """2.5th percentile of the posterior — lower bound of 95% credible interval."""
    ci_upper_days: float
    """97.5th percentile of the posterior — upper bound of 95% credible interval."""
    n_observations: int
    """Number of (t, R) pairs used (each 24h/7d check is one observation)."""
    population_informed: bool
    """True when individual retention data was available; False = pure prior sample."""


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
        description="Per-technique Ebbinghaus forgetting-curve fits (OLS). "
                    "Populated directly from measured retention data — not LLM-generated.",
    )
    technique_stability: List[BayesianStabilityStats] = Field(
        default_factory=list,
        description="Per-technique MCMC posterior over S under the hierarchical prior. "
                    "Provides credible intervals and uncertainty quantification.",
    )
    bandit_expected_rewards: dict = Field(
        default_factory=dict,
        description="LinUCB expected reward θ̂ᵀx per technique at neutral conditions. "
                    "Higher = bandit predicts better retention for this user's patterns.",
    )
