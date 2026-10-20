"""A fake LLM for development and tests: no network, no API key, no cost.

- With no script, it guesses a category from simple keywords and answers in
  the same JSON format a real LLM is asked for. Good enough for demos offline.
- With a script (a list of answers), it returns them one by one. Tests use this
  to simulate a real LLM sending broken JSON, so we can check our retry logic.
"""
import json


KEYWORDS = {
    "billing": ["invoice", "facture", "charged", "refund", "payment", "billing", "price", "vat"],
    "account_access": ["log in", "login", "password", "mot de passe", "locked", "2fa", "access", "sso"],
    "bug": ["crash", "error", "bug", "not loading", "broken", "freezes", "down", "fails"],
    "feature_request": ["would be great", "could you add", "please add", "feature", "it would help"],
}


class FakeLLM:
    def __init__(self, script: list[str] | None = None):
        self.name = "fake"
        self._script = list(script) if script else None
        self.calls = 0

    def complete(self, system: str, user: str) -> str:
        self.calls += 1
        if self._script is not None:
            return self._script.pop(0)

        text = user.lower()
        for category, words in KEYWORDS.items():
            if any(word in text for word in words):
                return json.dumps({"category": category, "confidence": 0.6,
                                   "reason": "keyword match (fake LLM)"})
        return json.dumps({"category": "other", "confidence": 0.3,
                           "reason": "no keyword matched (fake LLM)"})
