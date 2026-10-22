"""Classify a support ticket with an LLM, and never trust the answer blindly.

LLMs sometimes wrap JSON in ```code fences```, add a sentence before it,
invent a category, or return invalid JSON. So we:
  1. extract the JSON object from the answer,
  2. validate it against the `Classification` model,
  3. if it fails, ask again and include the exact error in the message,
  4. after the last retry, fall back to "other" and flag the ticket for a human.
"""
import json
import re

from pydantic import ValidationError

from app import config
from app.llm.base import LLMClient
from app.models import Category, Classification, TicketIn, TriageResult, Urgency

# Below this confidence, a human should check the ticket
REVIEW_THRESHOLD = 0.5

SYSTEM_PROMPT = f"""You are a support-ticket triage assistant for a software company.
Classify the ticket into exactly one category:
- bug: something is broken, crashes, shows errors or behaves incorrectly
- billing: invoices, payments, refunds, prices, subscriptions
- account_access: login, passwords, 2FA, locked accounts, permissions, adding/removing users
- feature_request: a request for new functionality or an improvement
- other: anything else (general questions, partnerships, thanks, press, GDPR...)

Then rate its urgency:
- high: the customer cannot work at all, many users are affected, money is being lost right now, or there is a security risk
- medium: something important is wrong but there is a workaround or limited impact
- low: questions, requests, small issues with no time pressure

Tickets may be in English or French. Always write the summary in English.
Answer with ONLY a JSON object, no other text:
{{"category": one of {[c.value for c in Category]},
  "urgency": one of {[u.value for u in Urgency]},
  "summary": "the problem in one short sentence (max 20 words)",
  "confidence": number between 0 and 1,
  "reason": "why you chose this category, one short sentence"}}"""


def build_user_message(ticket: TicketIn) -> str:
    return f"Subject: {ticket.subject}\n\nMessage:\n{ticket.body}"


def extract_json(text: str) -> dict:
    """Find the JSON object in the LLM's answer, even if it is wrapped in text or code fences."""
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        raise ValueError("no JSON object found in the answer")
    return json.loads(match.group(0))


def classify_ticket(ticket: TicketIn, llm: LLMClient,
                    max_retries: int = config.LLM_MAX_RETRIES) -> TriageResult:
    user_message = build_user_message(ticket)
    last_error = ""

    for attempt in range(1, max_retries + 2):  # first try + retries
        prompt = user_message
        if last_error:
            prompt += (f"\n\nYour previous answer was invalid: {last_error}\n"
                       "Reply again with ONLY the JSON object.")

        answer = llm.complete(SYSTEM_PROMPT, prompt)
        try:
            result = Classification(**extract_json(answer))
        except ValidationError as e:
            # Tell the LLM exactly which field is wrong, e.g. "category: Input should be 'bug', ..."
            last_error = "; ".join(
                f"{'.'.join(str(p) for p in err['loc'])}: {err['msg']}" for err in e.errors()
            )[:300]
            continue
        except ValueError as e:  # no JSON found, or invalid JSON syntax
            last_error = str(e)[:300]
            continue

        return TriageResult(
            **result.model_dump(),
            model=llm.name,
            attempts=attempt,
            needs_human_review=result.confidence < REVIEW_THRESHOLD,
        )

    # Every attempt failed: don't crash, hand the ticket to a human instead
    return TriageResult(
        category=Category.OTHER,
        urgency=Urgency.MEDIUM,  # unknown: don't ignore it, don't panic either
        summary=ticket.subject,
        confidence=0.0,
        reason=f"LLM output invalid after {max_retries + 1} attempts: {last_error}",
        model=llm.name,
        attempts=max_retries + 1,
        needs_human_review=True,
    )