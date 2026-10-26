import json

from app.llm.fake import FakeLLM
from app.models import Category, Team, TicketIn, Urgency
from app.triage.pipeline import triage_ticket
from app.triage.router import route
from app.triage.rules import RuleOutcome


def outcome(urgency="medium", review=False, rules=None):
    return RuleOutcome(final_urgency=Urgency(urgency), needs_human_review=review,
                       rules_applied=rules or [])


def test_each_category_goes_to_its_team():
    assert route(Category.BUG, outcome()).team == Team.ENGINEERING
    assert route(Category.BILLING, outcome()).team == Team.FINANCE
    assert route(Category.ACCOUNT_ACCESS, outcome()).team == Team.ACCOUNT_SUPPORT
    assert route(Category.FEATURE_REQUEST, outcome()).team == Team.PRODUCT
    assert route(Category.OTHER, outcome()).team == Team.GENERAL_SUPPORT


def test_sla_depends_on_urgency():
    assert route(Category.BUG, outcome("high")).sla_hours == 4
    assert route(Category.BUG, outcome("medium")).sla_hours == 24
    assert route(Category.BUG, outcome("low")).sla_hours == 72


def test_unsure_ai_goes_to_human_review():
    assert route(Category.BILLING, outcome(review=True)).team == Team.HUMAN_REVIEW


def test_security_goes_to_security_team_even_if_review_needed():
    routing = route(Category.ACCOUNT_ACCESS,
                    outcome("high", review=True, rules=["security_incident"]))
    assert routing.team == Team.SECURITY
    assert routing.sla_hours == 4


def test_full_pipeline_llm_then_rules_then_routing():
    """The LLM says 'medium', but 300 blocked employees makes it high: rules win."""
    ticket = TicketIn(customer_email="admin@city.fr", subject="Nobody can log in",
                      body="After the SSO change, none of our 300 employees can log in.")
    llm = FakeLLM([json.dumps({"category": "account_access", "urgency": "medium",
                               "summary": "SSO change blocks all logins",
                               "confidence": 0.9, "reason": "Login problem"})])

    triage, routing = triage_ticket(ticket, llm)

    assert triage.urgency == Urgency.MEDIUM          # what the LLM said
    assert routing.final_urgency == Urgency.HIGH     # after business rules
    assert routing.rules_applied == ["many_users_affected"]
    assert routing.team == Team.ACCOUNT_SUPPORT
    assert routing.sla_hours == 4