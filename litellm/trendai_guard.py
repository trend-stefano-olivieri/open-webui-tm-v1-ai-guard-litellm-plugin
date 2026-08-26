"""Local compatibility wrapper for the pinned TrendAI LiteLLM guardrail."""

from typing import Any, AsyncGenerator

from litellm.proxy._types import UserAPIKeyAuth
from litellm.proxy.proxy_server import StreamingCallbackError
from trendai_guard_upstream import TrendAIGuardrail as UpstreamTrendAIGuardrail


class TrendAIGuardrail(UpstreamTrendAIGuardrail):
    """Map policy-denied streams to a client error instead of HTTP 500."""

    async def async_post_call_streaming_iterator_hook(
        self,
        user_api_key_dict: UserAPIKeyAuth,
        response: Any,
        request_data: dict,
    ) -> AsyncGenerator[Any, None]:
        try:
            async for chunk in super().async_post_call_streaming_iterator_hook(
                user_api_key_dict=user_api_key_dict,
                response=response,
                request_data=request_data,
            ):
                yield chunk
        except StreamingCallbackError as exc:
            if getattr(exc, "status_code", None) is None:
                exc.status_code = 400
            raise
