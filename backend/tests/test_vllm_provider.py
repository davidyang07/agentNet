import asyncio
import json

import httpx
import pytest

from app.gateway.schemas import ModelProviderError, ModelRequest
from app.gateway.vllm_provider import VLLMProvider


def _request() -> ModelRequest:
    return ModelRequest(
        agent_id="agent-000",
        seed=1,
        tick=0,
        system_prompt="system prompt with secret",
        user_message="injection payload",
        max_tokens=64,
        mock_leak_probability=0.5,
    )


def _client_with_handler(handler) -> httpx.AsyncClient:
    transport = httpx.MockTransport(handler)
    return httpx.AsyncClient(transport=transport)


def test_sends_openai_compatible_request_shape():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["headers"] = dict(request.headers)
        captured["body"] = json.loads(request.content)
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": "hello"}}],
                "usage": {"total_tokens": 7},
            },
        )

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client,
                base_url="http://vllm.local:8000",
                api_key="secret-key",
                model_name="qwen-test",
            )
            return await provider.complete(_request())

    response = asyncio.run(run())

    assert captured["url"] == "http://vllm.local:8000/v1/chat/completions"
    assert captured["headers"]["authorization"] == "Bearer secret-key"
    assert captured["body"]["model"] == "qwen-test"
    assert captured["body"]["max_tokens"] == 64
    assert captured["body"]["messages"] == [
        {"role": "system", "content": "system prompt with secret"},
        {"role": "user", "content": "injection payload"},
    ]
    assert response.text == "hello"
    assert response.tokens_used == 7
    assert response.provider == "vllm"


def test_no_api_key_omits_auth_header():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["headers"] = dict(request.headers)
        return httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}]})

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            return await provider.complete(_request())

    asyncio.run(run())
    assert "authorization" not in captured["headers"]


def test_http_error_raises_model_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"error": "boom"})

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            await provider.complete(_request())

    with pytest.raises(ModelProviderError):
        asyncio.run(run())


def test_malformed_response_shape_raises_model_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            await provider.complete(_request())

    with pytest.raises(ModelProviderError):
        asyncio.run(run())


def test_connection_error_raises_model_provider_error():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused")

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            await provider.complete(_request())

    with pytest.raises(ModelProviderError):
        asyncio.run(run())


def test_falls_back_to_token_estimate_without_usage_field():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"choices": [{"message": {"content": "a" * 40}}]})

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            return await provider.complete(_request())

    response = asyncio.run(run())
    assert response.tokens_used == 10  # len("a"*40) // 4


def _complete_with(body: dict):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            return await provider.complete(_request())

    return asyncio.run(run())


def test_null_content_and_null_usage_are_an_empty_reply_not_a_crash():
    # OpenAI-compatible servers send "content": null for a reply with no text
    # (e.g. tool calls only). This used to raise TypeError from len(None),
    # which escaped the gateway and killed the experiment's tick loop.
    response = _complete_with({"choices": [{"message": {"content": None}}], "usage": None})
    assert response.text == ""
    assert response.tokens_used == 1


def test_null_usage_falls_back_to_token_estimate():
    response = _complete_with({"choices": [{"message": {"content": "a" * 40}}], "usage": None})
    assert response.tokens_used == 10


def test_non_string_content_raises_model_provider_error():
    with pytest.raises(ModelProviderError):
        _complete_with({"choices": [{"message": {"content": [{"type": "text", "text": "hi"}]}}]})



def _status(code: int):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(code, json={})

    async def run():
        async with _client_with_handler(handler) as client:
            provider = VLLMProvider(
                client, base_url="http://vllm.local:8000", api_key=None, model_name="qwen-test"
            )
            await provider.complete(_request())

    with pytest.raises(ModelProviderError) as excinfo:
        asyncio.run(run())
    return excinfo.value


def test_client_errors_are_not_retryable_but_overload_and_server_errors_are():
    # A 401/404 will fail identically on every retry; 429 and 5xx may not.
    assert _status(401).retryable is False
    assert _status(404).retryable is False
    assert _status(429).retryable is True
    assert _status(503).retryable is True


def test_an_unexpected_response_shape_is_not_retryable():
    with pytest.raises(ModelProviderError) as excinfo:
        _complete_with({"choices": [{"message": {"content": [{"type": "text"}]}}]})
    assert excinfo.value.retryable is False
