"""Provider-agnostic request/response shapes for the Model Gateway.
`ModelProvider` is the uniform interface both
`MockProvider` (deterministic, no I/O) and `VLLMProvider` (real HTTP against
an OpenAI-compatible vLLM endpoint) implement, so callers never need to know
which is behind a given `ModelGateway`.
"""

from typing import Literal, Protocol

from pydantic import BaseModel


class ModelRequest(BaseModel):
    agent_id: str
    seed: int
    tick: int
    system_prompt: str
    user_message: str
    max_tokens: int
    # Consumed only by MockProvider to decide its
    # canned outcome deterministically. Real providers ignore this entirely --
    # a real model decides its own output.
    mock_leak_probability: float
    purpose: str = "propagation"
    # The attacking agent. MockProvider keys its draw on it, so attacks from
    # different sources on one target are independent, like propagation's
    # infect:{source} draws (SPEC §3.4 rule 4). Real providers ignore it.
    source_agent_id: str | None = None


class ModelResponse(BaseModel):
    text: str
    latency_ms: float
    tokens_used: int
    provider: Literal["mock", "vllm"]


class ModelProviderError(Exception):
    """Raised by a provider on any HTTP/connection/parse failure. Caught only
    by ModelGateway, which retries it like a timeout -- unless `retryable` is
    False: a failure that would recur identically on every attempt (a 4xx
    other than 429, a malformed response) is given up on at once."""

    def __init__(self, message: str, *, retryable: bool = True) -> None:
        super().__init__(message)
        self.retryable = retryable


class ModelProvider(Protocol):
    async def complete(self, request: ModelRequest) -> ModelResponse: ...
