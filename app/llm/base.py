from dataclasses import dataclass
from typing import Protocol
 
 
class LLMError(Exception):
    """The LLM could not be reached or returned an unusable response."""
 
 
@dataclass
class Usage:
    requests: int = 0        # calls to complete()
    http_attempts: int = 0   # HTTP requests sent, including retries
    rate_limited: int = 0    # "429 Too Many Requests" answers we had to wait out
    input_tokens: int = 0
    output_tokens: int = 0
 
    def snapshot(self) -> "Usage":
        return Usage(**vars(self))
 
    def since(self, before: "Usage") -> "Usage":
        """What happened between `before` and now, e.g. for one ticket."""
        return Usage(**{k: getattr(self, k) - getattr(before, k) for k in vars(self)})
 
 
class LLMClient(Protocol):
    name: str
    usage: Usage
 
    def complete(self, system: str, user: str) -> str:
        """Send a system prompt and a user message, return the model's text answer."""
