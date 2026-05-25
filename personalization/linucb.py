"""
LinUCB contextual bandit for CogPrint technique recommendation.

Algorithm — Disjoint LinUCB (Li et al., 2010):
  For each arm k (study technique) independently:

    Ridge-regression model:
      θ̂_k = A_k⁻¹ b_k

      where   A_k = I_d + Σ x_t xᵀ_t          (d×d gram matrix, λ=1 ridge)
              b_k = Σ r_t x_t                   (d-dim reward-weighted context)

    Upper-confidence bound:
      UCB_k(x) = θ̂_k ᵀ x  +  α √(xᵀ A_k⁻¹ x)
                 ───────────    ───────────────────
                 exploitation     exploration bonus

    Recommendation:  argmax_k  UCB_k(x)

Why disjoint (not hybrid):
  Hybrid LinUCB shares a common parameter vector β across arms.  In our
  setting the baseline "quality" of a technique for a user is highly arm-
  specific (active recall ≠ re-reading) and we have a small arm set (7),
  so disjoint models capture per-technique learning without forcing a shared
  global structure that could cause negative transfer.

Context vector  (CONTEXT_DIM = 9):
  [0]   intercept       — constant 1.0
  [1]   sleep_norm      — sleep_hours / 10, clipped [0, 1]
  [2]   stress_norm     — (5 − stress_level) / 4   (inverted; lower stress→higher)
  [3]   morning         — one-hot: time_of_day == "morning"
  [4]   afternoon       — one-hot: time_of_day == "afternoon"
  [5]   evening         — one-hot: time_of_day == "evening"
  [6]   night           — one-hot: time_of_day == "night"
  [7]   duration_norm   — duration_minutes / 90, clipped [0, 1]
  [8]   session_norm    — log(session_number + 1) / log(101)  (≈0 early, ≈1 at 100)

Reward signal (retention-primary):
  Best available from retention checks for this session:
    7d score                          (gold standard)
    24h score × 0.85                  (conservative Ebbinghaus extrapolation)
    quiz_score × 0.70                 (weak signal: encoding quality, not forgetting)

Exploration parameter α = 1.2 (default):
  α controls the confidence–exploration tradeoff.  A value of 1.2 is the
  standard recommendation in Li et al. — it corresponds roughly to a 95%
  confidence interval for Gaussian rewards.  Increase for more exploration
  in early data; decrease once the bandit has ≥ 20 observations per arm.

Serialisation:
  A_k and b_k are stored as nested Python lists so the bandit state can be
  round-tripped through JSON (for the `bandit_state_json` DB column).
"""

from __future__ import annotations

import json
import math
from typing import Optional

import numpy as np

# ── Constants ──────────────────────────────────────────────────────────────────

CONTEXT_DIM: int = 9      # dimension of the feature vector
DEFAULT_ALPHA: float = 1.2  # exploration coefficient

# Study techniques supported by the bandit
ALL_TECHNIQUES: list[str] = [
    "spaced_repetition",
    "active_recall",
    "re_reading",
    "mind_maps",
    "interleaving",
    "elaborative_interrogation",
    "practice_testing",
]

# Neutral context used for "expected reward" display (median conditions)
_NEUTRAL_CONTEXT = np.array([
    1.0,   # intercept
    0.70,  # 7h sleep / 10
    0.50,  # moderate stress, inverted
    0.25,  # time-of-day: equal split → 0.25 each (not strictly one-hot, but
    0.25,  #   semantically correct for an "average" context display)
    0.25,
    0.25,
    0.50,  # 45-minute session / 90
    0.50,  # mid-study career
], dtype=float)


# ── Context builder ────────────────────────────────────────────────────────────

def build_context(
    sleep_hours:        Optional[float],
    stress_level:       Optional[float],
    time_of_day:        Optional[str],
    duration_minutes:   Optional[float],
    session_number:     int,
) -> np.ndarray:
    """
    Build the 9-dimensional context vector from session metadata.

    Missing values fall back to the neutral/median encoding so the bandit
    can still make an informed recommendation without penalising missing data.

    Parameters
    ----------
    sleep_hours      : hours slept the night before (0–12)
    stress_level     : self-reported stress 1–5
    time_of_day      : "morning" | "afternoon" | "evening" | "night"
    duration_minutes : planned/actual session length in minutes
    session_number   : 1-based index of this user's session (for exploration decay)

    Returns
    -------
    np.ndarray of shape (CONTEXT_DIM,)
    """
    x = np.zeros(CONTEXT_DIM, dtype=float)

    # [0] intercept
    x[0] = 1.0

    # [1] sleep: 7h is the neutral/healthy baseline
    x[1] = np.clip((sleep_hours or 7.0) / 10.0, 0.0, 1.0)

    # [2] stress (inverted): 1/5 = 1.0 (no stress → good learning), 5/5 = 0.0
    sl = stress_level if stress_level is not None else 3.0
    x[2] = np.clip((5.0 - sl) / 4.0, 0.0, 1.0)

    # [3-6] time-of-day one-hot
    tod_map = {"morning": 3, "afternoon": 4, "evening": 5, "night": 6}
    if time_of_day in tod_map:
        x[tod_map[time_of_day]] = 1.0
    else:
        # unknown → uniform 0.25 (softer than leaving zeros)
        x[3] = x[4] = x[5] = x[6] = 0.25

    # [7] duration: 90-minute session is roughly the cognitive limit
    x[7] = np.clip((duration_minutes or 45.0) / 90.0, 0.0, 1.0)

    # [8] session number: log-compress so early sessions get high exploration,
    #     later sessions approach 1.0 asymptotically
    x[8] = math.log(session_number + 1) / math.log(101.0)

    return x


def build_context_from_session(session, session_number: int) -> np.ndarray:
    """
    Convenience wrapper: extract fields directly from a StudySession ORM object.
    """
    return build_context(
        sleep_hours      = session.sleep_hours,
        stress_level     = session.stress_level,
        time_of_day      = session.time_of_day,
        duration_minutes = session.duration_minutes,
        session_number   = session_number,
    )


# ── Reward extraction ──────────────────────────────────────────────────────────

def best_available_reward(
    session_id: int,
    quiz_score: float,
    rc_index: dict,
) -> Optional[float]:
    """
    Return the best available reward signal for a completed session.

    Priority order:
      1. 7-day retention check         — true measure of durable learning
      2. 24h retention check × 0.85    — conservative Ebbinghaus extrapolation
                                          (R_7d ≈ R_24h · e^{−6/S} ≈ R_24h · 0.85
                                           for a typical S ≈ 30 days)
      3. Immediate quiz score × 0.70   — weak signal: encoding quality, not
                                          forgetting; heavily discounted

    Parameters
    ----------
    session_id  : DB primary key of the session
    quiz_score  : immediate quiz score [0, 1]
    rc_index    : {(session_id, check_type): score} from RetentionCheck records

    Returns
    -------
    Reward in [0, 1], or None if no signal at all.
    """
    r7d = rc_index.get((session_id, "7d"))
    if r7d is not None:
        return float(r7d)

    r24h = rc_index.get((session_id, "24h"))
    if r24h is not None:
        return float(r24h) * 0.85

    # Fall back to quiz score if no retention data yet
    if quiz_score is not None:
        return float(quiz_score) * 0.70

    return None


# ── LinUCB model ───────────────────────────────────────────────────────────────

class LinUCBRecommender:
    """
    Disjoint LinUCB bandit for study-technique recommendation.

    Each arm (technique) maintains its own ridge-regression matrices:
      A_k ∈ ℝ^{d×d}  (gram matrix + λI identity regulariser)
      b_k ∈ ℝ^d      (reward-weighted feature accumulator)

    Posterior mean and UCB are computed on demand from A_k⁻¹ b_k.

    Typical usage
    -------------
    bandit = LinUCBRecommender()

    # At start of each new session (before it happens):
    x = build_context(sleep=7.5, stress=2, tod="morning", dur=45, n=12)
    technique = bandit.recommend(x)

    # After session + retention check arrive:
    reward = best_available_reward(session_id, quiz, rc_index)
    if reward is not None:
        bandit.update(technique, x, reward)

    # Persist to DB:
    db_row.bandit_state_json = bandit.to_json()

    # Restore from DB:
    bandit = LinUCBRecommender.from_json(db_row.bandit_state_json)
    """

    def __init__(
        self,
        techniques: list[str] = ALL_TECHNIQUES,
        alpha: float = DEFAULT_ALPHA,
    ) -> None:
        self.techniques = list(techniques)
        self.alpha      = alpha
        d               = CONTEXT_DIM

        # Initialise with identity (ridge λ=1) and zero reward accumulator
        self._A: dict[str, np.ndarray] = {k: np.eye(d)          for k in techniques}
        self._b: dict[str, np.ndarray] = {k: np.zeros(d)        for k in techniques}

    # ── Core update ────────────────────────────────────────────────────────────

    def update(self, technique: str, context: np.ndarray, reward: float) -> None:
        """
        Incorporate one (context, reward) observation for the given arm.

        Updates:  A_k ← A_k + x xᵀ
                  b_k ← b_k + r x

        Parameters
        ----------
        technique : arm identifier (must be in self.techniques)
        context   : feature vector from build_context()
        reward    : scalar reward in [0, 1]
        """
        if technique not in self._A:
            # Gracefully handle a technique that wasn't in the initial list
            d = CONTEXT_DIM
            self._A[technique] = np.eye(d)
            self._b[technique] = np.zeros(d)
            if technique not in self.techniques:
                self.techniques.append(technique)

        x = context.reshape(-1)
        self._A[technique] += np.outer(x, x)
        self._b[technique] += reward * x

    # ── UCB scoring ────────────────────────────────────────────────────────────

    def ucb_scores(self, context: np.ndarray) -> dict[str, float]:
        """
        Compute UCB score for every arm given the current context.

        UCB_k(x) = θ̂_k ᵀ x  +  α √(xᵀ A_k⁻¹ x)

        where θ̂_k = A_k⁻¹ b_k.

        Returns dict mapping technique → UCB score.
        """
        x      = context.reshape(-1)
        scores = {}
        for k in self.techniques:
            A_inv  = np.linalg.inv(self._A[k])
            theta  = A_inv @ self._b[k]
            exploit = float(theta @ x)
            explore = float(self.alpha * math.sqrt(max(0.0, x @ A_inv @ x)))
            scores[k] = exploit + explore
        return scores

    def recommend(self, context: np.ndarray) -> str:
        """
        Return the technique with the highest UCB score.

        In the very first session (all arms are equal) ties are broken by
        alphabetical order — deterministic but not meaningful, so the first
        few sessions serve primarily as forced exploration.
        """
        scores = self.ucb_scores(context)
        return max(scores, key=lambda k: scores[k])

    # ── Expected-reward display (for Fingerprint page) ─────────────────────────

    def expected_rewards(
        self,
        context: Optional[np.ndarray] = None,
    ) -> dict[str, float]:
        """
        Return the estimated expected reward (θ̂ᵀx) for each technique —
        without the exploration bonus.  Used in the fingerprint display to
        show "which technique works best for you" without over-weighting arms
        that happen to be under-explored.

        Parameters
        ----------
        context : optional context vector; defaults to _NEUTRAL_CONTEXT
                  (a median user, moderate conditions) if not provided.
        """
        x = (_NEUTRAL_CONTEXT if context is None else context).reshape(-1)
        rewards = {}
        for k in self.techniques:
            theta     = np.linalg.inv(self._A[k]) @ self._b[k]
            rewards[k] = float(theta @ x)
        return rewards

    def observation_counts(self) -> dict[str, int]:
        """
        Return the number of reward observations incorporated for each arm.
        Computed as rank(A_k - I_d): each outer-product update adds rank 1
        to the gram matrix.

        Note: only approximate — two collinear updates can share a rank step.
        Use as a rough display count, not a strict guarantee.
        """
        d = CONTEXT_DIM
        counts = {}
        for k in self.techniques:
            # trace(A_k) = d (identity) + n (one unit added per outer product)
            # So n ≈ trace(A_k) - d
            counts[k] = max(0, round(float(np.trace(self._A[k])) - d))
        return counts

    # ── Batch refit from history ────────────────────────────────────────────────

    def fit_from_history(
        self,
        sessions,            # list[StudySession] — all sessions for this user
        retention_checks,    # list[RetentionCheck]
    ) -> None:
        """
        Refit the bandit from scratch using all historical sessions.

        Resets all A_k, b_k to the identity/zero prior and replays every
        (technique, context, reward) tuple in chronological order.

        This is the right approach when: (a) the context-vector definition
        changes, (b) you want a reproducible deterministic refit after a
        schema migration, or (c) the bandit state was lost and must be
        reconstructed from the DB.

        Parameters
        ----------
        sessions         : list of StudySession ORM objects, any order
                           (will be sorted by created_at internally)
        retention_checks : list of RetentionCheck ORM objects
        """
        # Reset to prior
        d = CONTEXT_DIM
        for k in self.techniques:
            self._A[k] = np.eye(d)
            self._b[k] = np.zeros(d)

        # Build retention-check index: (session_id, check_type) → score
        rc_index = {
            (rc.session_id, rc.check_type): rc.score
            for rc in retention_checks
        }

        # Sort sessions chronologically
        sorted_sessions = sorted(sessions, key=lambda s: s.created_at)

        for i, session in enumerate(sorted_sessions, start=1):
            reward = best_available_reward(
                session_id = session.id,
                quiz_score = session.quiz_score,
                rc_index   = rc_index,
            )
            if reward is None:
                continue  # no signal yet — skip; will be incorporated on next refit

            context = build_context_from_session(session, session_number=i)
            self.update(session.technique, context, reward)

    # ── Serialisation ──────────────────────────────────────────────────────────

    def to_dict(self) -> dict:
        """
        Serialise bandit state to a JSON-safe dict.

        Format:
          {
            "techniques": [...],
            "alpha": 1.2,
            "arms": {
              "active_recall": {"A": [[...], ...], "b": [...]},
              ...
            }
          }
        """
        return {
            "techniques": self.techniques,
            "alpha":      self.alpha,
            "arms": {
                k: {
                    "A": self._A[k].tolist(),
                    "b": self._b[k].tolist(),
                }
                for k in self.techniques
            },
        }

    @classmethod
    def from_dict(cls, data: dict) -> "LinUCBRecommender":
        """
        Restore bandit state from a previously serialised dict.
        """
        obj = cls(techniques=data["techniques"], alpha=data["alpha"])
        for k, arm in data["arms"].items():
            obj._A[k] = np.array(arm["A"], dtype=float)
            obj._b[k] = np.array(arm["b"], dtype=float)
        return obj

    def to_json(self) -> str:
        """Serialise to a JSON string suitable for a TEXT/VARCHAR DB column."""
        return json.dumps(self.to_dict())

    @classmethod
    def from_json(cls, s: str) -> "LinUCBRecommender":
        """Restore from a JSON string."""
        return cls.from_dict(json.loads(s))
