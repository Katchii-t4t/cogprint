import json
from typing import Optional

import anthropic

from schemas.fingerprint import FingerprintProfile
from schemas.session import KnowledgeMap, StudyPlanDay, StudyPlanResponse

AGENT3_SYSTEM_PROMPT = """\
You are a personalized study planner for CogPrint.

You receive two inputs:
1. A knowledge map of the material to be learned (from Agent 1)
2. A cognitive fingerprint of the learner (from Agent 2)

Your task: generate a day-by-day study plan that maximizes retention for THIS specific learner.

Rules:
- Prioritize techniques with highest 7-day retention in the learner's fingerprint
- Schedule sessions at the learner's optimal time of day when known
- Use spaced repetition principles: revisit concepts at increasing intervals (day 1, 3, 7, 14)
- Session duration should match the learner's optimal duration when known; default 45 minutes
- If fingerprint confidence is "low", use evidence-based defaults (active recall + spaced repetition)
- Each day entry must have: day, technique, topic_focus, session_duration_minutes, time_of_day, rationale

Return a JSON object with: user_id, total_days, days (list), general_advice.
"""


class StudyPlanner:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic()

    def generate_plan(
        self,
        user_id: int,
        knowledge_map: KnowledgeMap,
        fingerprint: FingerprintProfile,
        total_days: int = 14,
    ) -> StudyPlanResponse:
        km_json = knowledge_map.model_dump_json(indent=2)
        fp_json = fingerprint.model_dump_json(indent=2)

        response = self.client.messages.parse(
            model="claude-sonnet-4-6",
            max_tokens=6000,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": AGENT3_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"User ID: {user_id}\n"
                        f"Study duration: {total_days} days\n\n"
                        f"KNOWLEDGE MAP:\n{km_json}\n\n"
                        f"COGNITIVE FINGERPRINT:\n{fp_json}\n\n"
                        f"Generate the personalized study plan."
                    ),
                }
            ],
            output_format=StudyPlanResponse,
        )

        if response.parsed_output is not None:
            parsed = response.parsed_output
            parsed.user_id = user_id
            return parsed

        # Fallback: parse text block manually
        for block in response.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                    plan = StudyPlanResponse.model_validate(data)
                    plan.user_id = user_id
                    return plan
                except Exception:
                    break

        return StudyPlanResponse(
            user_id=user_id,
            total_days=total_days,
            days=[],
            general_advice="Study plan generation failed. Please try again.",
        )
