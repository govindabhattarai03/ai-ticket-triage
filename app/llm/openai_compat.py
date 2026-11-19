"""Client for any LLM that speaks the OpenAI "chat completions" format.

Both Gemini and Ollama offer this format, so one small class covers both.
"""
import time

import httpx

from app.llm.base import LLMError, Usage


class OpenAICompatibleClient:
    def __init__(self, base_url: str, model: str, api_key: str | None = None,
                 timeout: float = 30.0, max_attempts: int = 3):
        self.name = model
        self.usage = Usage()
        self._url = base_url.rstrip("/") + "/chat/completions"
        self._model = model
        self._headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._timeout = timeout
        self._max_attempts = max_attempts

    def complete(self, system: str, user: str) -> str:
        payload = {
            "model": self._model,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": user},
            ],
            "temperature": 0,  # same input -> (almost) same answer: better for classification
        }
        self.usage.requests += 1

        for attempt in range(1, self._max_attempts + 1):
            self.usage.http_attempts += 1
            try:
                response = httpx.post(self._url, json=payload, headers=self._headers,
                                      timeout=self._timeout)
            except httpx.HTTPError as e:
                error = f"network error: {e}"
            else:
                if response.status_code == 200:
                    body = response.json()
                    tokens = body.get("usage") or {}
                    self.usage.input_tokens += tokens.get("prompt_tokens", 0)
                    self.usage.output_tokens += tokens.get("completion_tokens", 0)
                    return body["choices"][0]["message"]["content"]
                if response.status_code == 429:
                    self.usage.rate_limited += 1
                if response.status_code not in (429, 500, 502, 503, 504):
                    # 400/401/403/404: retrying will not help (bad key, bad model name...)
                    raise LLMError(f"HTTP {response.status_code}: {response.text[:300]}")
                error = f"HTTP {response.status_code}: {response.text[:200]}"

            if attempt < self._max_attempts:
                time.sleep(2 ** attempt)  # wait 2s, then 4s: rate limits often clear quickly

        raise LLMError(f"LLM unavailable after {self._max_attempts} attempts ({error})")