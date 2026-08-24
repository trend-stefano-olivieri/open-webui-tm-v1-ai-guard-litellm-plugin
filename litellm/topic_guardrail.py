import os
from typing import Any, Literal, Optional

import httpx
from fastapi import HTTPException

from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)
from litellm.llms.custom_httpx.http_handler import (
    get_async_httpx_client,
    httpxSpecialProvider,
)
from litellm.types.utils import GenericGuardrailAPIInputs


class DeniedTopicsGuardrail(CustomGuardrail):
    """LiteLLM pre-call guardrail backed by the local topic-guard service."""

    def __init__(
        self,
        api_base: Optional[str] = None,
        policy_profile: Optional[str] = None,
        fallback_on_error: Literal["block", "allow"] = "block",
        timeout: float = 15.0,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.api_base = (api_base or os.getenv("TOPIC_GUARD_API_BASE") or "").rstrip("/")
        if not self.api_base:
            raise ValueError(
                "DeniedTopicsGuardrail requires api_base or TOPIC_GUARD_API_BASE"
            )
        self.policy_profile = policy_profile or os.getenv("TOPIC_POLICY_PROFILE")
        self.on_failure = fallback_on_error
        self.timeout = timeout
        verbose_proxy_logger.info(
            "Initialized denied-topic guard: guardrail_name=%s api_base=%s "
            "profile=%s on_failure=%s timeout=%s",
            self.guardrail_name,
            self.api_base,
            self.policy_profile or "policy default",
            self.on_failure,
            self.timeout,
        )

    @staticmethod
    def _message_as_dict(message: Any) -> dict[str, Any] | None:
        if isinstance(message, dict):
            return message
        model_dump = getattr(message, "model_dump", None)
        if callable(model_dump):
            value = model_dump()
            return value if isinstance(value, dict) else None
        return None

    def _get_latest_user_prompt(
        self, inputs: GenericGuardrailAPIInputs
    ) -> Optional[str]:
        messages = inputs.get("structured_messages")
        if isinstance(messages, list):
            for raw_message in reversed(messages):
                message = self._message_as_dict(raw_message)
                if not message or message.get("role") != "user":
                    continue
                content = message.get("content")
                if isinstance(content, str):
                    return content.strip() or None
                if isinstance(content, list):
                    parts = []
                    for item in content:
                        item_data = self._message_as_dict(item)
                        if not item_data:
                            continue
                        if item_data.get("type") in ("text", "input_text"):
                            text = item_data.get("text")
                            if isinstance(text, str):
                                parts.append(text)
                    return "".join(parts).strip() or None
                return None

        texts = inputs.get("texts")
        if isinstance(texts, list):
            prompt = "".join(item for item in texts if isinstance(item, str)).strip()
            return prompt or None
        return None

    def _handle_service_error(self, description: str) -> None:
        if self.on_failure == "allow":
            verbose_proxy_logger.warning(
                "Denied-topic guard unavailable; allowing request (fail-open): %s",
                description,
            )
            return
        verbose_proxy_logger.error(
            "Denied-topic guard unavailable; blocking request (fail-closed): %s",
            description,
        )
        raise HTTPException(
            status_code=503,
            detail={
                "error": "Denied-topic policy check unavailable; request blocked"
            },
        )

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: GenericGuardrailAPIInputs,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> GenericGuardrailAPIInputs:
        if input_type != "request":
            return inputs

        prompt = self._get_latest_user_prompt(inputs)
        if not prompt:
            self._handle_service_error("no user prompt could be extracted")
            return inputs

        body: dict[str, Any] = {
            "text": prompt,
            "model": request_data.get("model"),
        }
        if self.policy_profile:
            body["profile"] = self.policy_profile

        try:
            client = get_async_httpx_client(
                llm_provider=httpxSpecialProvider.GuardrailCallback
            )
            response = await client.post(
                f"{self.api_base}/v1/classify",
                json=body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = response.json()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 413:
                raise HTTPException(
                    status_code=400,
                    detail={
                        "error": (
                            "Blocked by topic policy. User message exceeds the "
                            "configured size limit"
                        )
                    },
                ) from exc
            self._handle_service_error(
                f"service returned HTTP {exc.response.status_code}"
            )
            return inputs
        except Exception as exc:
            self._handle_service_error(type(exc).__name__)
            return inputs

        if not isinstance(result, dict) or not isinstance(result.get("denied"), bool):
            self._handle_service_error("service returned an invalid response")
            return inputs

        if result["denied"]:
            matches = result.get("matches")
            labels = []
            if isinstance(matches, list):
                labels = [
                    match.get("label")
                    for match in matches
                    if isinstance(match, dict)
                    and isinstance(match.get("label"), str)
                    and match.get("label")
                ]
            label_text = ", ".join(labels) if labels else "configured denied topic"
            verbose_proxy_logger.info(
                "Denied-topic policy blocked request: topics=%s", label_text
            )
            raise HTTPException(
                status_code=400,
                detail={
                    "error": (
                        "Blocked by topic policy. Denied topic detected: "
                        f"{label_text}"
                    ),
                    "denied_topics": labels,
                },
            )

        return inputs
