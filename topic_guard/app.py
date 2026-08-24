from __future__ import annotations

import asyncio
import logging
import os
from contextlib import asynccontextmanager
from dataclasses import asdict

from fastapi import FastAPI, HTTPException, Request
from fastapi.concurrency import run_in_threadpool
from pydantic import BaseModel, ConfigDict, Field

from topic_guard.classifier import RequestTooLargeError, TopicClassifier
from topic_guard.policy import PolicyError, load_policy


LOGGER = logging.getLogger("topic_guard")
MODEL_PATH = os.getenv("TOPIC_MODEL_PATH", "/models/topic-model")
POLICY_PATH = os.getenv("TOPIC_POLICY_PATH", "/app/policies/topics.yaml")
DEFAULT_PROFILE = os.getenv("TOPIC_POLICY_PROFILE") or None


class ClassificationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    text: str = Field(min_length=1)
    profile: str | None = None
    model: str | None = None


@asynccontextmanager
async def lifespan(app: FastAPI):
    policy = load_policy(POLICY_PATH, DEFAULT_PROFILE)
    app.state.classifier = TopicClassifier(MODEL_PATH)
    app.state.inference_lock = asyncio.Lock()
    LOGGER.info(
        "Topic guard ready: model_path=%s policy_version=%s profile=%s topics=%s",
        MODEL_PATH,
        policy.version,
        policy.profile.name,
        len(policy.profile.denied_topics),
    )
    yield


app = FastAPI(
    title="OpenWebUI denied-topic guard",
    version="1.0.0",
    docs_url=None,
    redoc_url=None,
    lifespan=lifespan,
)


@app.get("/health")
async def health() -> dict:
    try:
        policy = load_policy(POLICY_PATH, DEFAULT_PROFILE)
    except PolicyError as exc:
        raise HTTPException(status_code=503, detail="invalid topic policy") from exc
    return {
        "status": "ok",
        "model_path": MODEL_PATH,
        "policy_version": policy.version,
        "profile": policy.profile.name,
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
