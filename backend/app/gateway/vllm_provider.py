"""Thin async client against vLLM's own OpenAI-compatible
`POST /v1/chat/completions` contract. No vLLM SDK,
no RunPod SDK -- a RunPod GPU pod running `vllm serve ...` is, from this
codebase's point of view, just an HTTP endpoint behind `settings.vllm_base_url`.
"""

from __future__ import annotations

import time

import httpx

from app.gateway.schemas import ModelProviderError, ModelRequest, ModelResponse

# Request timeout and rate limiting: the same request may succeed later.
_RETRYABLE_CLIENT_STATUSES = frozenset({408, 429})


def _is_retryable(exc: Exception) -> bool:
    """Connection failures, timeouts, 408/429 and 5xx may clear up on a retry.
    Any other 4xx (bad key, unknown model, oversized request) fails the same
    way every time, so retrying it only spends budget."""
    if isinstance(exc, httpx.HTTPStatusError):
        status = exc.response.status_code
        return status >= 500 or status in _RETRYABLE_CLIENT_STATUSES
    return True


def _describe(exc: Exception) -> str:
    if isinstance(exc, httpx.HTTPStatusError):
        return f"HTTP {exc.response.status_code}"
    return type(exc).__name__


class VLLMProvider:
    def __init__(
        self,
        client: httpx.AsyncClient,
        *,
        base_url: str,
        api_key: str | None,
        model_name: str,
    ) -> None:
        self._client = client
        self._base_url = base_url.rstrip("/")
        self._api_key = api_key
        self._model_name = model_name

    async def complete(self, request: ModelRequest) -> ModelResponse:
        headers = {"Authorization": f"Bearer {self._api_key}"} if self._api_key else {}
        payload = {
            "model": self._model_name,
            "messages": [
                {"role": "system", "content": request.system_prompt},
                {"role": "user", "content": request.user_message},
            ],
            "max_tokens": request.max_tokens,
        }
        start = time.monotonic()
        try:
            resp = await self._client.post(
                f"{self._base_url}/v1/chat/completions", json=payload, headers=headers
            )
            resp.raise_for_status()
            data = resp.json()
        except (httpx.HTTPError, ValueError) as exc:
            # Never log `payload`/`data` wholesale here -- system_prompt
            # embeds the target's confidential_token in plaintext.
            raise ModelProviderError(
                f"vLLM request failed for agent_id={request.agent_id}: {_describe(exc)}",
                retryable=_is_retryable(exc),
            ) from exc
        latency_ms = (time.monotonic() - start) * 1000

        try:
            text = data["choices"][0]["message"]["content"]
        except (KeyError, IndexError, TypeError) as exc:
            raise ModelProviderError(
                f"unexpected vLLM response shape for agent_id={request.agent_id}",
                retryable=False,
            ) from exc
        # OpenAI-compatible servers send "content": null for a reply with no
        # text (e.g. tool calls only) -- an empty reply, not a provider failure.
        if text is None:
            text = ""
        if not isinstance(text, str):
            raise ModelProviderError(
                f"unexpected vLLM response shape for agent_id={request.agent_id}",
                retryable=False,
            )

        usage = data.get("usage")
        total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None
        if isinstance(total_tokens, int) and total_tokens > 0:
            tokens_used = total_tokens
        else:
            tokens_used = max(1, len(text) // 4)

        return ModelResponse(
            text=text,
            latency_ms=latency_ms,
            tokens_used=tokens_used,
            provider="vllm",
        )
