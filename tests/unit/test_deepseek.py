import asyncio
import json

import httpx
import pytest

from prompt_architect.llm.credentials import CredentialStore
from prompt_architect.llm.deepseek import DeepSeekProvider, ProviderError


class MemoryKeyring:
    def __init__(self) -> None:
        self.values: dict[tuple[str, str], str] = {}

    def get_password(self, service: str, username: str):
        return self.values.get((service, username))

    def set_password(self, service: str, username: str, value: str) -> None:
        self.values[(service, username)] = value

    def delete_password(self, service: str, username: str) -> None:
        self.values.pop((service, username), None)


def test_lists_models_and_parses_structured_completion() -> None:
    backend = MemoryKeyring()
    credentials = CredentialStore(backend)
    credentials.set("test-secret-value")

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == "Bearer test-secret-value"
        if request.url.path == "/models":
            return httpx.Response(200, json={"data": [{"id": "deepseek-example", "owned_by": "deepseek"}]})
        payload = json.loads(request.content)
        assert payload["response_format"] == {"type": "json_object"}
        return httpx.Response(
            200,
            json={
                "choices": [{"message": {"content": '{"ok":true}'}}],
                "usage": {"prompt_tokens": 3, "completion_tokens": 2, "total_tokens": 5},
            },
        )

    provider = DeepSeekProvider(credentials, transport=httpx.MockTransport(handler))
    assert [item.id for item in asyncio.run(provider.list_models())] == ["deepseek-example"]
    payload, usage = asyncio.run(provider.complete_json(
        [{"role": "user", "content": "test"}], model="deepseek-example"
    ))
    assert payload == {"ok": True}
    assert usage.total_tokens == 5


def test_maps_invalid_key_without_leaking_it() -> None:
    secret = "test-secret-never-log"

    def handler(_: httpx.Request) -> httpx.Response:
        return httpx.Response(401, json={"error": {"message": f"bad {secret}"}})

    provider = DeepSeekProvider(transport=httpx.MockTransport(handler))
    with pytest.raises(ProviderError) as caught:
        asyncio.run(provider.test_key(secret))
    assert caught.value.code == "invalid_api_key"
    assert secret not in str(caught.value)


def test_environment_key_takes_precedence(monkeypatch) -> None:
    backend = MemoryKeyring()
    backend.set_password("PromptArchitectAgent", "deepseek-api-key", "stored-key")
    monkeypatch.setenv("DEEPSEEK_API_KEY", "environment-key")
    credential = CredentialStore(backend).get()
    assert credential.value == "environment-key"
    assert credential.source == "environment"
