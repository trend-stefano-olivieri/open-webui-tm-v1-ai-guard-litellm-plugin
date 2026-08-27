from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from grounding.policy import GroundingPolicyError, load_grounding_policy
from topic_guard.classifier import RequestTooLargeError, TopicClassifier
from topic_guard.grounding import GroundingClassifier
from topic_guard.policy import PolicyError, load_policy


LOGGER = logging.getLogger("topic_guard")
MODEL_PATH = os.getenv("TOPIC_MODEL_PATH", "/models/topic-model")
POLICY_PATH = os.getenv("TOPIC_POLICY_PATH", "/app/policies/topics.yaml")
DEFAULT_PROFILE = os.getenv("TOPIC_POLICY_PROFILE") or None
GROUNDING_MODEL_PATH = os.getenv(
    "GROUNDING_MODEL_PATH", "/models/grounding-model"
)
GROUNDING_POLICY_PATH = os.getenv(
    "GROUNDING_POLICY_PATH", "/app/policies/grounding.yaml"
)


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    profile: str | None = None
    model: str | None = None


class GroundingRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = ""
    sources: list[str] = Field(min_length=1)
    answer: str = Field(min_length=1)


@asynccontextmanager
async def lifespan(app: FastAPI):
    policy = load_policy(POLICY_PATH, DEFAULT_PROFILE)
    grounding_policy = load_grounding_policy(GROUNDING_POLICY_PATH)
    app.state.classifier = TopicClassifier(MODEL_PATH)
    app.state.grounding_classifier = GroundingClassifier(GROUNDING_MODEL_PATH)
    app.state.inference_lock = asyncio.Lock()
    LOGGER.info(
        "Topic guard ready: model_path=%s policy_version=%s profile=%s topics=%s",
        MODEL_PATH,
        policy.version,
        policy.profile.name,
        len(policy.profile.denied_topics),
    )
    LOGGER.info(
        "Grounding evaluator ready: model_path=%s policy_version=%s",
        GROUNDING_MODEL_PATH,
        grounding_policy.version,
    )
    yield


app = FastAPI(
    title="OpenWebUI local policy guard",
    version="1.1.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    try:
        policy = load_policy(POLICY_PATH, DEFAULT_PROFILE)
        grounding_policy = load_grounding_policy(GROUNDING_POLICY_PATH)
    except (PolicyError, GroundingPolicyError) as exc:
        raise HTTPException(status_code=503, detail="invalid local policy") from exc
    return {
        "status": "ok",
        "topic_model_path": MODEL_PATH,
        "topic_policy_version": policy.version,
        "topic_profile": policy.profile.name,
        "grounding_model_path": GROUNDING_MODEL_PATH,
        "grounding_policy_version": grounding_policy.version,
    }


@app.post("/v1/classify")
async def classify(payload: ClassificationRequest, request: Request) -> dict:
    try:
        policy = load_policy(POLICY_PATH, payload.profile or DEFAULT_PROFILE)
    except PolicyError as exc:
        LOGGER.error("Topic policy validation failed: %s", exc)
        raise HTTPException(status_code=503, detail="invalid topic policy") from exc

    try:
        async with request.app.state.inference_lock:
            result = await run_in_threadpool(
                request.app.state.classifier.classify,
                payload.text,
                policy.profile,
            )
    except RequestTooLargeError as exc:
        LOGGER.warning("Topic policy blocked a request above its configured size limit")
        raise HTTPException(
            status_code=413, detail="request exceeds topic policy size limit"
        ) from exc
    except Exception as exc:
        LOGGER.exception("Topic classification failed without logging prompt content")
        raise HTTPException(status_code=503, detail="topic classification failed") from exc

    return {
        "denied": result.denied,
        "matches": [asdict(match) for match in result.matches],
        "scores": [asdict(score) for score in result.scores],
        "policy_version": policy.version,
        "profile": policy.profile.name,
    }


@app.post("/v1/grounding")
async def evaluate_grounding(payload: GroundingRequest, request: Request) -> dict:
    try:
        policy = load_grounding_policy(GROUNDING_POLICY_PATH)
    except GroundingPolicyError as exc:
        LOGGER.error("Grounding policy validation failed: %s", exc)
        raise HTTPException(status_code=503, detail="invalid grounding policy") from exc

    try:
        async with request.app.state.inference_lock:
            result = await run_in_threadpool(
                request.app.state.grounding_classifier.evaluate,
                payload.sources,
                payload.answer,
                policy,
            )
    except Exception as exc:
        LOGGER.exception("Grounding evaluation failed without logging content")
        raise HTTPException(status_code=503, detail="grounding evaluation failed") from exc

    return {
        "score": result.score,
        "supported_claims": result.supported_claims,
        "total_claims": result.total_claims,
        "claim_scores": result.claim_scores,
        "input_truncated": result.input_truncated,
        "policy_version": policy.version,
    }
