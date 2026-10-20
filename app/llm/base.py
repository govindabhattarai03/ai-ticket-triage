"""The interface every LLM client follows.

The rest of the app only knows about `complete(system, user) -> str`.
That means we can switch between Gemini, a local Ollama model or a fake
model for tests without touching the triage logic.
"""
from typing import Protocol


class LLMError(Exception):
    """The LLM could not be reached or returned an unusable response."""


class LLMClient(Protocol):
    name: str

    def complete(self, system: str, user: str) -> str:
        """Send a system prompt and a user message, return the model's text answer."""
        ...
