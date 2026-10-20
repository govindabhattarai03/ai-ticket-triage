"""Test the real HTTP client against a fake server (httpx.MockTransport): no key, no network."""
import httpx
import pytest

from app.llm import openai_compat
from app.llm.base import LLMError
from app.llm.openai_compat import OpenAICompatibleClient


def use_fake_server(monkeypatch, responses):
    """Make httpx.post return the given responses one by one, and record the requests."""
    requests = []

    def handler(request):
        requests.append(request)
        return responses.pop(0)

    fake_client = httpx.Client(transport=httpx.MockTransport(handler))

    def fake_post(url, json=None, headers=None, timeout=None):
        return fake_client.post(url, json=json, headers=headers)

    monkeypatch.setattr(openai_compat.httpx, "post", fake_post)
    monkeypatch.setattr(openai_compat.time, "sleep", lambda seconds: None)  # don't wait in tests
    return requests


def ok(text):
    return httpx.Response(200, json={"choices": [{"message": {"content": text}}]})


def test_sends_openai_format_and_returns_text(monkeypatch):
    requests = use_fake_server(monkeypatch, [ok("hello")])
    client = OpenAICompatibleClient("https://example.com/v1", "my-model", api_key="secret")

    assert client.complete("system prompt", "user message") == "hello"
    sent = requests[0]
    assert str(sent.url) == "https://example.com/v1/chat/completions"
    assert sent.headers["Authorization"] == "Bearer secret"
    assert b'"model":"my-model"' in sent.content.replace(b" ", b"")


def test_retries_on_rate_limit(monkeypatch):
    requests = use_fake_server(monkeypatch, [httpx.Response(429), ok("done")])
    client = OpenAICompatibleClient("https://example.com/v1", "m")
    assert client.complete("s", "u") == "done"
    assert len(requests) == 2


def test_does_not_retry_on_bad_key(monkeypatch):
    requests = use_fake_server(monkeypatch, [httpx.Response(401, text="invalid key")])
    client = OpenAICompatibleClient("https://example.com/v1", "m")
    with pytest.raises(LLMError, match="401"):
        client.complete("s", "u")
    assert len(requests) == 1
