from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Any, Iterable


SOURCE_PATTERN = re.compile(
    r"<source\b[^>]*>(.*?)</source>", re.IGNORECASE | re.DOTALL
)
USER_QUERY_PATTERN = re.compile(
    r"<user_query\b[^>]*>(.*?)</user_query>", re.IGNORECASE | re.DOTALL
)
CONTEXT_PATTERN = re.compile(
    r"<context\b[^>]*>.*?</context>", re.IGNORECASE | re.DOTALL
)


@dataclass(frozen=True)
class GroundingContext:
    query: str
    sources: tuple[str, ...]
    sources_truncated: bool


def message_as_dict(message: Any) -> dict[str, Any] | None:
    if isinstance(message, dict):
        return message
    model_dump = getattr(message, "model_dump", None)
    if callable(model_dump):
        value = model_dump()
        return value if isinstance(value, dict) else None
    return None


def content_as_text(content: Any) -> str:
    if isinstance(content, str):
        return content
    if not isinstance(content, list):
        return ""
    parts: list[str] = []
    for raw_item in content:
        item = message_as_dict(raw_item)
        if not item or item.get("type") not in ("text", "input_text"):
            continue
        text = item.get("text")
        if isinstance(text, str):
            parts.append(text)
    return "".join(parts)


def extract_user_query_from_text(text: str) -> str:
    query_matches = USER_QUERY_PATTERN.findall(text)
    if query_matches:
        return unescape(query_matches[-1]).strip()

    without_sources = SOURCE_PATTERN.sub("", text)
    without_context = CONTEXT_PATTERN.sub("", without_sources)
    return unescape(without_context).strip()


def extract_latest_user_query(messages: Iterable[Any]) -> str:
    for raw_message in reversed(list(messages)):
        message = message_as_dict(raw_message)
        if not message or str(message.get("role", "")).lower() != "user":
            continue
        text = content_as_text(message.get("content"))
        return extract_user_query_from_text(text)
    return ""


def extract_grounding_context(
    messages: Iterable[Any],
    max_source_characters: int,
    max_query_characters: int,
    trusted_source_roles: tuple[str, ...] = ("system",),
) -> GroundingContext:
    message_list = list(messages)
    query = extract_latest_user_query(message_list)[:max_query_characters]
    trusted_roles = {role.lower() for role in trusted_source_roles}

    raw_sources: list[str] = []
    for raw_message in message_list:
        message = message_as_dict(raw_message)
        if not message or str(message.get("role", "")).lower() not in trusted_roles:
            continue
        text = content_as_text(message.get("content"))
        for match in SOURCE_PATTERN.findall(text):
            source = unescape(match).strip()
            if source and source not in raw_sources:
                raw_sources.append(source)

    sources: list[str] = []
    used_characters = 0
    sources_truncated = False
    for source in raw_sources:
        remaining = max_source_characters - used_characters
        if remaining <= 0:
            sources_truncated = True
            break
        if len(source) > remaining:
            sources.append(source[:remaining])
            used_characters += remaining
            sources_truncated = True
            break
        sources.append(source)
        used_characters += len(source)

    return GroundingContext(
        query=query,
        sources=tuple(sources),
        sources_truncated=sources_truncated,
    )
