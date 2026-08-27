import copy
import os
from typing import Any, AsyncGenerator, Literal, Optional

import httpx
from pydantic import BaseModel, Field

from grounding.context import GroundingContext, extract_grounding_context
from grounding.policy import (
    GroundingPolicy,
    GroundingPolicyError,
    load_grounding_policy,
)
from grounding.render import (
    GroundingAssessment,
    append_annotation,
    render_annotation,
)
from litellm._logging import verbose_proxy_logger
from litellm.integrations.custom_guardrail import (
    CustomGuardrail,
    log_guardrail_information,
)
from litellm.llms.custom_httpx.http_handler import (
    get_async_httpx_client,
    httpxSpecialProvider,
)
from litellm.proxy._types import UserAPIKeyAuth
from litellm.types.utils import (
    GenericGuardrailAPIInputs,
    ModelResponse,
    ModelResponseStream,
)


class GroundingServiceResponse(BaseModel):
    score: float = Field(ge=0.0, le=1.0)
    supported_claims: int = Field(ge=0)
    total_claims: int = Field(ge=0)
    input_truncated: bool = False


class GroundingAnnotationGuardrail(CustomGuardrail):
    """Append a local, source-based grounding assessment to model responses."""

    def __init__(
        self,
        api_base: Optional[str] = None,
        policy_path: Optional[str] = None,
        timeout: float = 30.0,
        **kwargs: Any,
    ):
        super().__init__(**kwargs)
        self.api_base = (
            api_base or os.getenv("GROUNDING_GUARD_API_BASE") or ""
        ).rstrip("/")
        if not self.api_base:
            raise ValueError(
                "GroundingAnnotationGuardrail requires api_base or "
                "GROUNDING_GUARD_API_BASE"
            )
        self.policy_path = policy_path or os.getenv(
            "GROUNDING_POLICY_PATH", "/app/policies/grounding.yaml"
        )
        self.timeout = timeout
        load_grounding_policy(self.policy_path)
        verbose_proxy_logger.info(
            "Initialized grounding annotation guard: guardrail_name=%s "
            "api_base=%s policy_path=%s timeout=%s",
            self.guardrail_name,
            self.api_base,
            self.policy_path,
            self.timeout,
        )

    @staticmethod
    def _request_messages(request_data: dict) -> list[Any]:
        messages = request_data.get("messages")
        return messages if isinstance(messages, list) else []

    def _context(
        self, request_data: dict, policy: GroundingPolicy
    ) -> GroundingContext:
        return extract_grounding_context(
            self._request_messages(request_data),
            max_source_characters=policy.max_source_characters,
            max_query_characters=policy.max_query_characters,
            trusted_source_roles=("system",),
        )

    @staticmethod
    def _parse_service_response(payload: Any) -> GroundingServiceResponse:
        if not isinstance(payload, dict):
            raise ValueError("grounding service returned a non-object response")
        model_validate = getattr(GroundingServiceResponse, "model_validate", None)
        if callable(model_validate):
            result = model_validate(payload)
        else:
            result = GroundingServiceResponse(**payload)
        if result.supported_claims > result.total_claims:
            raise ValueError("grounding service returned inconsistent claim counts")
        return result

    async def _evaluate(
        self,
        answer: str,
        context: GroundingContext,
        policy: GroundingPolicy,
    ) -> GroundingAssessment | None:
        if not context.sources:
            if not policy.annotate_no_sources:
                return None
            return GroundingAssessment(state="not_evaluated")

        request_body = {
            "query": context.query,
            "sources": list(context.sources),
            "answer": answer,
        }

        try:
            client = get_async_httpx_client(
                llm_provider=httpxSpecialProvider.GuardrailCallback
            )
            response = await client.post(
                f"{self.api_base}/v1/grounding",
                json=request_body,
                timeout=self.timeout,
            )
            response.raise_for_status()
            result = self._parse_service_response(response.json())
            return GroundingAssessment(
                state="evaluated",
                score=result.score,
                supported_claims=result.supported_claims,
                total_claims=result.total_claims,
                input_truncated=context.sources_truncated or result.input_truncated,
            )
        except httpx.HTTPStatusError as exc:
            verbose_proxy_logger.warning(
                "Grounding evaluation service returned HTTP %s",
                exc.response.status_code,
            )
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Grounding evaluation unavailable without logging content: %s",
                type(exc).__name__,
            )

        if policy.annotate_on_error:
            return GroundingAssessment(state="unavailable")
        return None

    async def _annotation(
        self,
        answer: str,
        request_data: dict,
        policy: GroundingPolicy,
        context: GroundingContext,
    ) -> str | None:
        assessment = await self._evaluate(answer, context, policy)
        if assessment is None:
            return None
        return render_annotation(assessment, policy)

    @log_guardrail_information
    async def apply_guardrail(
        self,
        inputs: GenericGuardrailAPIInputs,
        request_data: dict,
        input_type: Literal["request", "response"],
        logging_obj: Optional[Any] = None,
    ) -> GenericGuardrailAPIInputs:
        if input_type != "response":
            return inputs

        try:
            policy = load_grounding_policy(self.policy_path)
        except GroundingPolicyError as exc:
            verbose_proxy_logger.error("Invalid grounding policy: %s", exc)
            return inputs

        context = self._context(request_data, policy)
        texts = inputs.get("texts")
        if not isinstance(texts, list):
            return inputs

        annotated_texts: list[str] = []
        for text in texts:
            if not isinstance(text, str):
                annotated_texts.append(text)
                continue
            assessment = await self._evaluate(text, context, policy)
            annotated_texts.append(
                append_annotation(text, assessment, policy)
                if assessment is not None
                else text
            )
        inputs["texts"] = annotated_texts
        return inputs

    @staticmethod
    def _chunk_text(chunk: ModelResponseStream | ModelResponse) -> dict[int, str]:
        result: dict[int, str] = {}
        for choice in getattr(chunk, "choices", []) or []:
            delta = getattr(choice, "delta", None)
            message = getattr(choice, "message", None)
            content = (
                getattr(delta, "content", None)
                if delta is not None
                else getattr(message, "content", None)
            )
            if isinstance(content, str) and content:
                index = getattr(choice, "index", 0) or 0
                result[index] = result.get(index, "") + content
        return result

    @staticmethod
    def _is_terminal_chunk(chunk: Any) -> bool:
        choices = getattr(chunk, "choices", None)
        if not choices:
            return True
        return any(getattr(choice, "finish_reason", None) is not None for choice in choices)

    @staticmethod
    def _annotation_chunk(template: Any, choice_index: int, annotation: str) -> Any:
        chunk = copy.deepcopy(template)
        matching_choices = [
            choice
            for choice in getattr(chunk, "choices", []) or []
            if (getattr(choice, "index", 0) or 0) == choice_index
        ]
        if not matching_choices:
            raise ValueError("no streaming choice template for grounding annotation")
        choice = matching_choices[0]
        chunk.choices = [choice]
        choice.finish_reason = None
        delta = getattr(choice, "delta", None)
        if delta is None:
            raise ValueError("streaming choice template has no delta")
        delta.content = annotation
        for field in ("role", "tool_calls", "function_call", "audio"):
            if hasattr(delta, field):
                setattr(delta, field, None)
        if hasattr(chunk, "usage"):
            chunk.usage = None
        return chunk

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
        request_data: dict,
    ) -> AsyncGenerator[Any, None]:
        answers: dict[int, str] = {}
        templates: dict[int, Any] = {}
        terminal_chunks: list[Any] = []

        async for chunk in response:
            for choice_index, text in self._chunk_text(chunk).items():
                answers[choice_index] = answers.get(choice_index, "") + text
                templates[choice_index] = chunk
            if self._is_terminal_chunk(chunk):
                terminal_chunks.append(chunk)
            else:
                yield chunk

        try:
            policy = load_grounding_policy(self.policy_path)
            context = self._context(request_data, policy)
            for choice_index in sorted(answers):
                annotation = await self._annotation(
                    answers[choice_index], request_data, policy, context
                )
                template = templates.get(choice_index)
                if annotation and template is not None:
                    yield self._annotation_chunk(template, choice_index, annotation)
        except Exception as exc:
            verbose_proxy_logger.warning(
                "Streaming grounding annotation skipped without logging content: %s",
                type(exc).__name__,
            )

        for chunk in terminal_chunks:
            yield chunk
