"""A fake LLM for development and tests: no network, no API key, no cost.

- With no script, it guesses a category from simple keywords and answers in
  the same JSON format a real LLM is asked for. Good enough for demos offline.
- With a script (a list of answers), it returns them one by one. Tests use this
  to simulate a real LLM sending broken JSON, so we can check our retry logic.
"""
import json

from app.llm.base import Usage


KEYWORDS = {
    "billing": ["invoice", "facture", "charged", "refund", "payment", "billing", "price", "vat"],
    "account_access": ["log in", "login", "password", "mot de passe", "locked", "2fa", "access", "sso"],
    "bug": ["crash", "error", "bug", "not loading", "broken", "freezes", "down", "fails"],
    "feature_request": ["would be great", "could you add", "please add", "feature", "it would help"],
}

URGENT_WORDS = ["urgent", "down", "right now", "cannot work", "losing", "immediately", "bloqué"]


class FakeLLM:
    def __init__(self, script: list[str] | None = None):
        self.name = "fake"
        self.usage = Usage()
        self._script = list(script) if script else None
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        self.usage.requests += 1
        self.usage.http_attempts += 1
        self.usage.input_tokens += (len(system) + len(user)) // 4   # rough: ~4 characters per token
        if self._script is not None:
            answer = self._script.pop(0)
            self.usage.output_tokens += len(answer) // 4
            return answer

        text = user.lower()
        urgency = "high" if any(w in text for w in URGENT_WORDS) else "medium"
        summary = user.splitlines()[0].removeprefix("Subject: ")[:200] or "Support request"
        answer = json.dumps({"category": "other", "urgency": "low", "summary": summary,
                             "confidence": 0.3, "reason": "no keyword matched (fake LLM)"})
        for category, words in KEYWORDS.items():
            if any(word in text for word in words):
                answer = json.dumps({"category": category, "urgency": urgency, "summary": summary,
                                     "confidence": 0.6, "reason": "keyword match (fake LLM)"})
                break
        self.usage.output_tokens += len(answer) // 4
        return answer