from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any

import yaml


class PolicyError(ValueError):
    """Raised when a denied-topic policy is invalid."""


@dataclass(frozen=True)
class DeniedTopic:
    id: str
    label: str
    classifier_label: str
    description: str


@dataclass(frozen=True)
class TopicProfile:
    name: str
    threshold: float
    chunk_characters: int
    chunk_overlap: int
    max_request_characters: int
    hypothesis_template: str
    denied_topics: tuple[DeniedTopic, ...]


@dataclass(frozen=True)
class TopicPolicy:
    version: int
    default_profile: str
    profile: TopicProfile


def _require_mapping(value: Any, path: str) -> dict[str, Any]:
    if not isinstance(value, dict):
        raise PolicyError(f"{path} must be a mapping")
    return value


def _require_text(value: Any, path: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PolicyError(f"{path} must be a non-empty string")
    return value.strip()


def load_policy(path: str | Path, requested_profile: str | None = None) -> TopicPolicy:
    policy_path = Path(path)
    try:
        raw = yaml.safe_load(policy_path.read_text(encoding="utf-8"))
    except (OSError, yaml.YAMLError) as exc:
        raise PolicyError(f"cannot load policy {policy_path}: {exc}") from exc

    document = _require_mapping(raw, "policy")
    version = document.get("version")
    if not isinstance(version, int) or isinstance(version, bool) or version < 1:
        raise PolicyError("version must be a positive integer")

    default_profile = _require_text(document.get("default_profile"), "default_profile")
    profiles = _require_mapping(document.get("profiles"), "profiles")
    profile_name = requested_profile or default_profile
    if profile_name not in profiles:
        raise PolicyError(f"unknown policy profile: {profile_name}")

    profile_data = _require_mapping(profiles[profile_name], f"profiles.{profile_name}")

    threshold = profile_data.get("threshold")
    if not isinstance(threshold, (int, float)) or isinstance(threshold, bool):
        raise PolicyError(f"profiles.{profile_name}.threshold must be a number")
    threshold = float(threshold)
    if threshold < 0.0 or threshold > 1.0:
        raise PolicyError(f"profiles.{profile_name}.threshold must be between 0 and 1")

    chunk_characters = profile_data.get("chunk_characters", 4096)
    if (
        not isinstance(chunk_characters, int)
        or isinstance(chunk_characters, bool)
        or chunk_characters < 1
    ):
        raise PolicyError(f"profiles.{profile_name}.chunk_characters must be positive")

    chunk_overlap = profile_data.get("chunk_overlap", 256)
    if (
        not isinstance(chunk_overlap, int)
        or isinstance(chunk_overlap, bool)
        or chunk_overlap < 0
        or chunk_overlap >= chunk_characters
    ):
        raise PolicyError(
            f"profiles.{profile_name}.chunk_overlap must be at least 0 and less "
            "than chunk_characters"
        )

    max_request_characters = profile_data.get("max_request_characters", 32768)
    if (
        not isinstance(max_request_characters, int)
        or isinstance(max_request_characters, bool)
        or max_request_characters < chunk_characters
    ):
        raise PolicyError(
            f"profiles.{profile_name}.max_request_characters must be at least "
            "chunk_characters"
        )

    hypothesis_template = _require_text(
        profile_data.get("hypothesis_template", "This request is about {}."),
        f"profiles.{profile_name}.hypothesis_template",
    )
    if "{}" not in hypothesis_template:
        raise PolicyError(
            f"profiles.{profile_name}.hypothesis_template must contain '{{}}'"
        )

    raw_topics = profile_data.get("denied_topics")
    if not isinstance(raw_topics, list) or not raw_topics:
        raise PolicyError(f"profiles.{profile_name}.denied_topics must be a non-empty list")

    topics: list[DeniedTopic] = []
    seen_ids: set[str] = set()
    seen_classifier_labels: set[str] = set()
    for index, raw_topic in enumerate(raw_topics):
        topic_path = f"profiles.{profile_name}.denied_topics[{index}]"
        topic_data = _require_mapping(raw_topic, topic_path)
        topic = DeniedTopic(
            id=_require_text(topic_data.get("id"), f"{topic_path}.id"),
            label=_require_text(topic_data.get("label"), f"{topic_path}.label"),
            classifier_label=_require_text(
                topic_data.get("classifier_label"), f"{topic_path}.classifier_label"
            ),
            description=_require_text(
                topic_data.get("description"), f"{topic_path}.description"
            ),
        )
        if topic.id in seen_ids:
            raise PolicyError(f"duplicate topic id: {topic.id}")
        if topic.classifier_label in seen_classifier_labels:
            raise PolicyError(f"duplicate classifier_label: {topic.classifier_label}")
        seen_ids.add(topic.id)
        seen_classifier_labels.add(topic.classifier_label)
        topics.append(topic)

    return TopicPolicy(
        version=version,
        default_profile=default_profile,
        profile=TopicProfile(
            name=profile_name,
            threshold=threshold,
            chunk_characters=chunk_characters,
            chunk_overlap=chunk_overlap,
            max_request_characters=max_request_characters,
            hypothesis_template=hypothesis_template,
            denied_topics=tuple(topics),
        ),
    )
