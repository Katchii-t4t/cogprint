import json

import anthropic

from schemas.session import KnowledgeConcept, KnowledgeMap

AGENT1_SYSTEM_PROMPT = """\
You are a learning content analyst for CogPrint.

Given a piece of learning material, extract its key concepts and produce a structured knowledge map.

For each concept identify:
- concept: clear, concise name
- difficulty: "foundational" | "intermediate" | "advanced"
- concept_type: "factual" (memorizable fact) | "conceptual" (understanding/principle) | "procedural" (how-to/process)
- related_concepts: list of other concepts in this material it connects to

Also provide a suggested_study_order: the optimal sequence for a learner to approach these concepts \
(foundational → advanced, prerequisite concepts first).

Return a JSON object with fields: title, total_concepts, concepts (list), suggested_study_order (list of concept names).
"""


class MaterialAnalyzer:
    def __init__(self) -> None:
        self.client = anthropic.Anthropic()

    def analyze(self, title: str, raw_text: str) -> KnowledgeMap:
        response = self.client.messages.parse(
            model="claude-sonnet-4-6",
            max_tokens=4096,
            thinking={"type": "adaptive"},
            system=[
                {
                    "type": "text",
                    "text": AGENT1_SYSTEM_PROMPT,
                    "cache_control": {"type": "ephemeral"},
                }
            ],
            messages=[
                {
                    "role": "user",
                    "content": (
                        f"Material title: {title}\n\n"
                        f"Content:\n{raw_text}\n\n"
                        f"Return the knowledge map JSON."
                    ),
                }
            ],
            output_format=KnowledgeMap,
        )

        if response.parsed_output is not None:
            return response.parsed_output

        # Fallback: parse text block manually
        for block in response.content:
            if block.type == "text":
                try:
                    data = json.loads(block.text)
                    return KnowledgeMap.model_validate(data)
                except Exception:
                    break

        # Minimal fallback
        return KnowledgeMap(
            title=title,
            total_concepts=0,
            concepts=[],
            suggested_study_order=[],
        )
