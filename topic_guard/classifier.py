from __future__ import annotations

from dataclasses import dataclass
from typing import Any

from topic_guard.policy import TopicProfile


@dataclass(frozen=True)
class TopicScore:
    id: str
    label: str
    score: float


@dataclass(frozen=True)
class ClassificationResult:
    denied: bool
    matches: tuple[TopicScore, ...]
    scores: tuple[TopicScore, ...]


class RequestTooLargeError(ValueError):
    """Raised when an input exceeds the policy's bounded scan size."""


class TopicClassifier:
    def __init__(self, model_path: str, pipeline_instance: Any | None = None):
        self.model_path = model_path
        if pipeline_instance is not None:
            self._pipeline = pipeline_instance
            return

        from transformers import (
            AutoModelForSequenceClassification,
            AutoTokenizer,
            pipeline,
        )

        tokenizer = AutoTokenizer.from_pretrained(model_path, local_files_only=True)
        model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True
        )
        model.float()
        model.eval()
        self._pipeline = pipeline(
            "zero-shot-classification",
            model=model,
            tokenizer=tokenizer,
            device=-1,
        )

    def classify(self, text: str, profile: TopicProfile) -> ClassificationResult:
        candidate_labels = [topic.classifier_label for topic in profile.denied_topics]
        if len(text) > profile.max_request_characters:
            raise RequestTooLargeError(
                "request exceeds topic policy max_request_characters"
            )

        step = profile.chunk_characters - profile.chunk_overlap
        chunks = [
            text[start : start + profile.chunk_characters]
            for start in range(0, len(text), step)
        ]
        score_by_classifier_label = {label: 0.0 for label in candidate_labels}

        for chunk in chunks:
            result = self._pipeline(
                chunk,
                candidate_labels=candidate_labels,
                hypothesis_template=profile.hypothesis_template,
                multi_label=True,
            )

            raw_labels = result.get("labels", []) if isinstance(result, dict) else []
            raw_scores = result.get("scores", []) if isinstance(result, dict) else []
            if len(raw_labels) != len(candidate_labels) or len(raw_scores) != len(
                candidate_labels
            ):
                raise RuntimeError("topic model returned an incomplete classification result")

            chunk_scores: dict[str, float] = {}
            for label, score in zip(raw_labels, raw_scores):
                if label not in candidate_labels:
                    raise RuntimeError("topic model returned an unknown classifier label")
                score_value = float(score)
                if score_value < 0.0 or score_value > 1.0:
                    raise RuntimeError("topic model returned a score outside [0, 1]")
                chunk_scores[label] = score_value

            if len(chunk_scores) != len(candidate_labels):
                raise RuntimeError("topic model returned duplicate classifier labels")
            for label, score in chunk_scores.items():
                score_by_classifier_label[label] = max(
                    score_by_classifier_label[label], score
                )

        scores = tuple(
            sorted(
                (
                    TopicScore(
                        id=topic.id,
                        label=topic.label,
                        score=score_by_classifier_label[topic.classifier_label],
                    )
                    for topic in profile.denied_topics
                ),
                key=lambda item: item.score,
                reverse=True,
            )
        )
        matches = tuple(item for item in scores if item.score >= profile.threshold)
        return ClassificationResult(denied=bool(matches), matches=matches, scores=scores)
