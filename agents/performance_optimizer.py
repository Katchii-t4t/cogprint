import json

import anthropic

from schemas.fingerprint import ConfidenceLevel, FingerprintProfile

AGENT2_SYSTEM_PROMPT = """\
You are a cognitive performance analyst for CogPrint, a personalized learning system.

Your job: analyze a learner's historical study data and produce a structured cognitive fingerprint — \
a precise, evidence-based profile of how THIS specific person learns best.

## Confidence calibration (strictly enforced)
- "low"   (<5 sessions):  Generic guidance only. Do NOT recommend specific techniques or conditions. \
List data_gaps explaining what data is still needed.
- "medium" (5–15 sessions): Moderate personalization. Only recommend techniques observed ≥2 times. \
Acknowledge uncertainty in insights.
- "high"  (16+ sessions): Strong personalization. Make confident, data-driven recommendations. \
Cross-validate patterns across multiple signals.

## Metric priority
RETENTION IS THE PRIMARY METRIC:
  7-day retention > 24h retention > immediate quiz score

If 7-day data is unavailable for a technique, weight 24h retention. \
Only use immediate scores as a last resort. \
Clearly note in data_gaps when retention data is sparse.

## Forgetting-curve data (pre-fitted Ebbinghaus R(t) = e^(−t/S))
The data block contains a FORGETTING-CURVE FITS section with measured S values.
S (stability, days) is fitted directly from the user's retention checkpoints — it is
ground-truth data, not an estimate. Use it as follows:
- Rank techniques by S when 7-day retention data is sparse.
- A technique with high immediate score but low S is MISLEADING: the learner
  remembers right after studying but forgets fast. Penalise it in your rankings.
- Quote S values explicitly in insights:
  e.g. "Active recall (S=14.2 d) retains material 3× longer than re-reading (S=4.7 d)."
- Use optimal_review_interval_days to populate recommended conditions.
- If a technique has no curve data, note it in data_gaps.

## Correlation interpretation (Pearson r)
- |r| < 0.2 → negligible
- 0.2–0.4 → weak
- 0.4–0.6 → moderate
- 0.6–0.8 → strong
- |r| > 0.8 → very strong
Positive sleep_score_correlation → more sleep → better performance.
Negative stress_score_correlation → lower stress → better performance.

## Output rules
- technique_effectiveness: include every technique observed, ranked best→worst by 7d retention
- relative_effectiveness: assign "best" only to top performer, "poor" only to clear underperformer
- insights: concrete, specific, actionable (e.g., "Active recall at 0.84 avg 7-day retention outperforms \
re-reading at 0.61 by 38%")
- data_gaps: be explicit (e.g., "No 7-day retention data for mind_maps — 3 sessions observed")
- improving_over_time: true if weekly trajectory Pearson r > 0.3, false if < -0.3, null if unclear
- avg_score_trend_per_week: estimated score change per week (positive = improving)
- If session_count < 5, set recommended_techniques and optimal_conditions fields to empty/null
"""


class PerformanceOptimizer:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic()

    def build_fingerprint(self, user_context: str, session_count: int) -> FingerprintProfile:
        if session_count == 0:
            return FingerprintProfile(
                session_count=0,
                confidence=ConfidenceLevel.LOW,
                data_gaps=["No sessions recorded yet. Complete at least 5 sessions to unlock personalization."],
            )

        user_message = (
            f"Analyze this learner's study data and generate their cognitive fingerprint.\n\n"
            f"{user_context}\n\n"
            f"Return a JSON object matching the FingerprintProfile schema exactly."
        )

        response = self.client.messages.parse(
            model="claude-opus-4-7",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            output_config={"effort": "high"},
            system=[
                {
                    "type": "text",
                    "text": AGENT2_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[{"role": "user", "content": user_message}],
            output_format=FingerprintProfile,
        )

        if response.parsed_output is not None:
            # Always override session_count with the ground-truth value from DB
            parsed = response.parsed_output
            parsed.session_count = session_count
            return parsed

        # Fallback: parse text block manually if .parsed_output is None
        for block in response.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                    profile = FingerprintProfile.model_validate(data)
                    profile.session_count = session_count
                    return profile
                except Exception:
                    break

        # Last resort: return minimal profile with correct session count
        return FingerprintProfile(
            session_count=session_count,
            confidence=self._confidence_from_count(session_count),
            data_gaps=["Analysis failed — will retry on next session."],
        )

    @staticmethod
    def _confidence_from_count(n: int) -> ConfidenceLevel:
        if n < 5:
            return ConfidenceLevel.LOW
        if n < 16:
            return ConfidenceLevel.MEDIUM
        return ConfidenceLevel.HIGH
