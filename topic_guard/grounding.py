from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Protocol, Sequence

from grounding.policy import GroundingPolicy


_SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[.!?])\s+|\n+")
_MARKDOWN_PREFIX_RE = re.compile(r"^\s*(?:[-*+]\s+|\d+[.)]\s+|#{1,6}\s+)")
_SOURCE_ATTRIBUTION_PREFIX_RE = re.compile(
    r"^\s*(?:"
    r"(?:(?:according to|based on|per)\s+(?:the\s+)?"
    r"(?:(?:provided|retrieved|available)\s+)?"
    r"(?:source(?:s)?|context|document(?:s)?|information)\s*[,;:]?\s*)"
    r"|(?:(?:the\s+)?(?:source(?:s)?|document(?:s)?)\s+"
    r"(?:states?|indicates?|reports?|says?)\s+(?:that\s+)?)"
    r")",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class GroundingResult:
    score: float
    supported_claims: int
    total_claims: int
    claim_scores: tuple[float, ...]
    input_truncated: bool


class EntailmentPredictor(Protocol):
    def predict(
        self,
        pairs: Sequence[tuple[str, str]],
        batch_size: int,
    ) -> list[float]: ...


class TorchEntailmentPredictor:
    def __init__(self, model_path: str):
        import torch
        from transformers import AutoModelForSequenceClassification, AutoTokenizer

        self._torch = torch
        self._tokenizer = AutoTokenizer.from_pretrained(
            model_path, local_files_only=True
        )
        self._model = AutoModelForSequenceClassification.from_pretrained(
            model_path, local_files_only=True
        )
        self._model.float()
        self._model.eval()

        label_to_id = {
            str(label).lower(): int(label_id)
            for label, label_id in self._model.config.label2id.items()
        }
        if "entailment" not in label_to_id:
            raise ValueError("grounding model does not define an entailment label")
        self._entailment_id = label_to_id["entailment"]

    def predict(
        self,
        pairs: Sequence[tuple[str, str]],
        batch_size: int,
    ) -> list[float]:
        scores: list[float] = []
        for start in range(0, len(pairs), batch_size):
            batch = pairs[start : start + batch_size]
            premises = [premise for premise, _ in batch]
            hypotheses = [hypothesis for _, hypothesis in batch]
            inputs = self._tokenizer(
                premises,
                hypotheses,
                padding=True,
                truncation=True,
                max_length=512,
                return_tensors="pt",
            )
            with self._torch.inference_mode():
                logits = self._model(**inputs).logits
                probabilities = self._torch.softmax(logits, dim=-1)
            scores.extend(
                float(value)
                for value in probabilities[:, self._entailment_id].tolist()
            )
        return scores


def _bounded_text(text: str, limit: int) -> tuple[str, bool]:
    normalized = text.strip()
    if len(normalized) <= limit:
        return normalized, False
    return normalized[:limit], True


def _split_claims(answer: str, max_claims: int) -> tuple[list[str], bool]:
    claims: list[str] = []
    for raw_segment in _SENTENCE_BOUNDARY_RE.split(answer):
        segment = _MARKDOWN_PREFIX_RE.sub("", raw_segment).strip()
        segment = _SOURCE_ATTRIBUTION_PREFIX_RE.sub("", segment).strip()
        if len(segment) < 2 or not any(character.isalnum() for character in segment):
            continue
        claims.append(segment)
    return claims[:max_claims], len(claims) > max_claims


def _source_chunks(
    sources: Sequence[str],
    max_source_characters: int,
    chunk_characters: int,
    chunk_overlap: int,
    max_chunks: int,
) -> tuple[list[str], bool]:
    remaining = max_source_characters
    chunks: list[str] = []
    truncated = False
    step = chunk_characters - chunk_overlap

    for source_index, source in enumerate(sources):
        normalized = source.strip()
        if not normalized:
            continue
        if remaining <= 0:
            truncated = True
            break
        bounded = normalized[:remaining]
        if len(normalized) > remaining:
            truncated = True
        remaining -= len(bounded)
        for start in range(0, len(bounded), step):
            chunk = bounded[start : start + chunk_characters].strip()
            if chunk and chunk not in chunks:
                chunks.append(chunk)
            if len(chunks) >= max_chunks:
                if start + chunk_characters < len(bounded):
                    truncated = True
                break
        if len(chunks) >= max_chunks:
            if any(item.strip() for item in sources[source_index + 1 :]):
                truncated = True
            break

    return chunks, truncated


class GroundingClassifier:
    def __init__(
        self,
        model_path: str,
        predictor: EntailmentPredictor | None = None,
    ):
        self.model_path = model_path
        self._predictor = predictor or TorchEntailmentPredictor(model_path)

    def evaluate(
        self,
        sources: Sequence[str],
        answer: str,
        policy: GroundingPolicy,
    ) -> GroundingResult:
        bounded_answer, answer_truncated = _bounded_text(
            answer, policy.max_answer_characters
        )
        claims, claims_truncated = _split_claims(
            bounded_answer, policy.max_claims
        )
        chunks, sources_truncated = _source_chunks(
            sources,
            policy.max_source_characters,
            policy.source_chunk_characters,
            policy.source_chunk_overlap,
            policy.max_source_chunks,
        )
        input_truncated = answer_truncated or claims_truncated or sources_truncated

        if not claims:
            return GroundingResult(1.0, 0, 0, (), input_truncated)
        if not chunks:
            return GroundingResult(
                0.0, 0, len(claims), tuple(0.0 for _ in claims), input_truncated
            )

        pairs = [(source, claim) for claim in claims for source in chunks]
        pair_scores = self._predictor.predict(pairs, policy.inference_batch_size)
        if len(pair_scores) != len(pairs):
            raise RuntimeError("grounding model returned an incomplete result")
        if any(score < 0.0 or score > 1.0 for score in pair_scores):
            raise RuntimeError("grounding model returned a score outside [0, 1]")

        claim_scores = tuple(
            max(pair_scores[index : index + len(chunks)])
            for index in range(0, len(pair_scores), len(chunks))
        )
        supported_claims = sum(
            score >= policy.claim_support_threshold for score in claim_scores
        )
        return GroundingResult(
            score=supported_claims / len(claims),
            supported_claims=supported_claims,
            total_claims=len(claims),
            claim_scores=claim_scores,
            input_truncated=input_truncated,
        )
