from __future__ import annotations

from dataclasses import dataclass

from grounding.policy import GroundingPolicy


ANNOTATION_MARKER = "<!-- grounding-check -->"


@dataclass(frozen=True)
class GroundingAssessment:
    state: str
    score: float | None = None
    supported_claims: int = 0
    total_claims: int = 0
    input_truncated: bool = False


def render_annotation(
    assessment: GroundingAssessment, policy: GroundingPolicy
) -> str:
    if assessment.state == "not_evaluated":
        summary = "ℹ️ **Grounding:** Not evaluated — no retrieved sources were supplied."
    elif assessment.state == "unavailable":
        summary = (
            "⚠️ **Grounding:** Evaluation unavailable; the answer was not blocked."
        )
    else:
        score = assessment.score if assessment.score is not None else 0.0
        percentage = round(score * 100)
        if score >= policy.grounded_threshold:
            result = "✅ Supported by retrieved sources"
        elif score >= policy.partial_threshold:
            result = "⚠️ Partially supported by retrieved sources"
        else:
            result = "❗ Potential hallucination or unsupported content"

        claim_summary = ""
        if assessment.total_claims > 0:
            claim_summary = (
                f" · {assessment.supported_claims}/{assessment.total_claims} "
                "claims supported"
            )
        summary = f"🛡️ **Grounding:** {result} — **{percentage}%**{claim_summary}."
        if assessment.input_truncated:
            summary += " Evaluation input was truncated."

    lines = ["", "---", ANNOTATION_MARKER, f"> {summary}"]
    if policy.show_disclaimer and assessment.state not in (
        "not_evaluated",
        "unavailable",
    ):
        lines.append(
            "> _This estimates support from retrieved sources; it does not prove "
            "real-world truth._"
        )
    return "\n".join(lines)


def append_annotation(
    answer: str, assessment: GroundingAssessment, policy: GroundingPolicy
) -> str:
    if ANNOTATION_MARKER in answer:
        return answer
    return answer.rstrip() + "\n" + render_annotation(assessment, policy)
