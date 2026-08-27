from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class GroundingPolicyError(ValueError):
    """Raised when the grounding annotation policy is invalid."""


@dataclass(frozen=True)
class GroundingPolicy:
    version: int
    grounded_threshold: float
    partial_threshold: float
    claim_support_threshold: float
    max_source_characters: int
    max_query_characters: int
    max_answer_characters: int
    source_chunk_characters: int
    source_chunk_overlap: int
    max_source_chunks: int
    max_claims: int
    inference_batch_size: int
    annotate_no_sources: bool
    annotate_on_error: bool
    show_disclaimer: bool


def _number(value: Any, path: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise GroundingPolicyError(f"{path} must be a number")
    result = float(value)
    if result < 0.0 or result > 1.0:
        raise GroundingPolicyError(f"{path} must be between 0 and 1")
    return result


def _positive_integer(value: Any, path: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool) or value < 1:
        raise GroundingPolicyError(f"{path} must be a positive integer")
    return value


def _boolean(value: Any, path: str) -> bool:
    if not isinstance(value, bool):
        raise GroundingPolicyError(f"{path} must be true or false")
    return value


def load_grounding_policy(path: str | Path) -> GroundingPolicy:
    policy_path = Path(path)
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise GroundingPolicyError(f"cannot load policy {policy_path}: {exc}") from exc
    if not isinstance(raw, dict):
        raise GroundingPolicyError("grounding policy must be a mapping")

    version = raw.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise GroundingPolicyError("version must be a positive integer")

    thresholds = raw.get("thresholds")
    if not isinstance(thresholds, dict):
        raise GroundingPolicyError("thresholds must be a mapping")
    grounded_threshold = _number(
        thresholds.get("grounded"), "thresholds.grounded"
    )
    partial_threshold = _number(thresholds.get("partial"), "thresholds.partial")
    if partial_threshold >= grounded_threshold:
        raise GroundingPolicyError(
            "thresholds.partial must be less than thresholds.grounded"
        )

    evaluation = raw.get("evaluation")
    if not isinstance(evaluation, dict):
        raise GroundingPolicyError("evaluation must be a mapping")
    claim_support_threshold = _number(
        evaluation.get("claim_support"), "evaluation.claim_support"
    )

    limits = raw.get("limits")
    if not isinstance(limits, dict):
        raise GroundingPolicyError("limits must be a mapping")

    annotations = raw.get("annotations")
    if not isinstance(annotations, dict):
        raise GroundingPolicyError("annotations must be a mapping")

    source_chunk_characters = _positive_integer(
        limits.get("source_chunk_characters"), "limits.source_chunk_characters"
    )
    source_chunk_overlap = limits.get("source_chunk_overlap")
    if (
        not isinstance(source_chunk_overlap, int)
        or isinstance(source_chunk_overlap, bool)
        or source_chunk_overlap < 0
        or source_chunk_overlap >= source_chunk_characters
    ):
        raise GroundingPolicyError(
            "limits.source_chunk_overlap must be at least 0 and less than "
            "limits.source_chunk_characters"
        )

    return GroundingPolicy(
        version=version,
        grounded_threshold=grounded_threshold,
        partial_threshold=partial_threshold,
        claim_support_threshold=claim_support_threshold,
        max_source_characters=_positive_integer(
            limits.get("max_source_characters"), "limits.max_source_characters"
        ),
        max_query_characters=_positive_integer(
            limits.get("max_query_characters"), "limits.max_query_characters"
        ),
        max_answer_characters=_positive_integer(
            limits.get("max_answer_characters"), "limits.max_answer_characters"
        ),
        source_chunk_characters=source_chunk_characters,
        source_chunk_overlap=source_chunk_overlap,
        max_source_chunks=_positive_integer(
            limits.get("max_source_chunks"), "limits.max_source_chunks"
        ),
        max_claims=_positive_integer(limits.get("max_claims"), "limits.max_claims"),
        inference_batch_size=_positive_integer(
            limits.get("inference_batch_size"), "limits.inference_batch_size"
        ),
        annotate_no_sources=_boolean(
            annotations.get("no_sources"), "annotations.no_sources"
        ),
        annotate_on_error=_boolean(
            annotations.get("evaluation_error"), "annotations.evaluation_error"
        ),
        show_disclaimer=_boolean(
            annotations.get("show_disclaimer"), "annotations.show_disclaimer"
        ),
    )
