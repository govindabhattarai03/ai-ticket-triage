import json

import pytest

from app.llm.fake import FakeLLM
from app.models import Category, TicketIn, Urgency
from app.triage.classifier import classify_ticket, extract_json

TICKET = TicketIn(
    customer_email="claire@pharmaplus.fr",
    subject="Facture incorrecte",
    body="Notre facture de septembre indique 25 licences au lieu de 20.",
)
GOOD = json.dumps({"category": "billing", "urgency": "medium", "summary": "Invoice shows 25 licences instead of 20",
                   "confidence": 0.9, "reason": "Invoice error"})


def test_valid_answer_on_first_try():
    llm = FakeLLM([GOOD])
    result = classify_ticket(TICKET, llm)
    assert result.category == Category.BILLING
    assert result.urgency == Urgency.MEDIUM
    assert result.summary == "Invoice shows 25 licences instead of 20"
    assert result.attempts == 1
    assert result.needs_human_review is False
    assert llm.calls == 1


@pytest.mark.parametrize("wrapped", [
    f"```json\n{GOOD}\n```",                 # code fences
    f"Here is the classification: {GOOD}",   # chatty prefix
])
def test_json_is_extracted_from_messy_answers(wrapped):
    assert classify_ticket(TICKET, FakeLLM([wrapped])).category == Category.BILLING


def test_retries_after_invalid_answer():
    llm = FakeLLM(["I think this is about billing.", GOOD])
    result = classify_ticket(TICKET, llm)
    assert result.category == Category.BILLING
    assert result.attempts == 2


def test_unknown_category_is_rejected_and_retried():
    bad = json.dumps({"category": "invoice", "urgency": "medium", "summary": "x", "confidence": 0.9, "reason": "x"})
    llm = FakeLLM([bad, GOOD])
    assert classify_ticket(TICKET, llm).attempts == 2


def test_falls_back_to_human_review_after_all_retries():
    llm = FakeLLM(["not json"] * 3)
    result = classify_ticket(TICKET, llm, max_retries=2)
    assert result.category == Category.OTHER
    assert result.needs_human_review is True
    assert llm.calls == 3


def test_low_confidence_needs_human_review():
    unsure = json.dumps({"category": "bug", "urgency": "low", "summary": "x", "confidence": 0.3, "reason": "unclear"})
    assert classify_ticket(TICKET, FakeLLM([unsure])).needs_human_review is True


def test_extract_json_raises_without_object():
    with pytest.raises(ValueError):
        extract_json("no braces here")


def test_missing_urgency_is_rejected_and_retried():
    no_urgency = json.dumps({"category": "billing", "summary": "x", "confidence": 0.9, "reason": "x"})
    llm = FakeLLM([no_urgency, GOOD])
    assert classify_ticket(TICKET, llm).attempts == 2


def test_fallback_keeps_subject_as_summary_and_medium_urgency():
    result = classify_ticket(TICKET, FakeLLM(["not json"] * 3), max_retries=2)
    assert result.urgency == Urgency.MEDIUM
    assert result.summary == TICKET.subject