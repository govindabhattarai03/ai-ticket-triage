import json
from pathlib import Path

from app.models import Category, TicketIn, TriageResult, Urgency
from app.triage.rules import apply_rules


def ticket(subject: str, body: str) -> TicketIn:
    return TicketIn(customer_email="client@example.com", subject=subject, body=body)


def llm_said(category: str, urgency: str) -> TriageResult:
    """Pretend the LLM returned this category and urgency."""
    return TriageResult(category=category, urgency=urgency, summary="x", confidence=0.9,
                        reason="x", model="test", attempts=1, needs_human_review=False)


def test_security_is_always_high_and_reviewed_by_a_human():
    t = ticket("Suspicious login", "An admin got an alert about a login from abroad. We may have been hacked.")
    outcome = apply_rules(t, llm_said("account_access", "medium"))
    assert outcome.final_urgency == Urgency.HIGH
    assert outcome.needs_human_review is True
    assert "security_incident" in outcome.rules_applied


def test_security_in_french_with_accents():
    t = ticket("Compte piraté", "Je pense que mon compte a été piraté, connexion suspecte cette nuit.")
    assert apply_rules(t, llm_said("account_access", "low")).final_urgency == Urgency.HIGH


def test_many_users_blocked_raises_to_high():
    t = ticket("SSO broken", "After the certificate change, none of our 300 employees can log in.")
    outcome = apply_rules(t, llm_said("account_access", "medium"))
    assert outcome.final_urgency == Urgency.HIGH
    assert outcome.rules_applied == ["many_users_affected"]


def test_customer_urgent_raises_low_to_medium_only():
    t = ticket("Invoice copy", "Please send me last month's invoice, it's urgent for our accountant.")
    outcome = apply_rules(t, llm_said("billing", "low"))
    assert outcome.final_urgency == Urgency.MEDIUM
    assert outcome.rules_applied == ["customer_marked_urgent"]


def test_feature_request_is_never_high():
    t = ticket("Dark mode", "Please add a dark mode, it's really urgent for our designers!")
    outcome = apply_rules(t, llm_said("feature_request", "high"))
    assert outcome.final_urgency == Urgency.MEDIUM
    assert "feature_request_capped" in outcome.rules_applied


def test_feature_request_for_many_users_is_not_an_outage():
    t = ticket("Multi-currency", "Supporting more currencies would let us roll out to all branches.")
    outcome = apply_rules(t, llm_said("feature_request", "low"))
    assert outcome.final_urgency == Urgency.LOW
    assert outcome.rules_applied == []


def test_no_rule_keeps_the_llm_decision():
    t = ticket("Export bug", "The PDF export closes the app since yesterday's update.")
    outcome = apply_rules(t, llm_said("bug", "medium"))
    assert outcome.final_urgency == Urgency.MEDIUM
    assert outcome.rules_applied == []


def test_rules_never_break_a_correct_label_in_the_dataset():
    """Start from the correct answers of the 50 labelled tickets: the rules must not change any."""
    path = Path(__file__).parent.parent / "data" / "sample_tickets.jsonl"
    for line in path.read_text(encoding="utf-8").splitlines():
        row = json.loads(line)
        t = ticket(row["subject"], row["body"])
        outcome = apply_rules(t, llm_said(row["expected_category"], row["expected_urgency"]))
        assert outcome.final_urgency == Urgency(row["expected_urgency"]), row["id"]