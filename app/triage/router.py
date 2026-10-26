"""Decide which team handles a ticket and how fast they must answer.

This is a plain lookup table, not AI: routing must be predictable, and a manager
can change who handles what by editing one dictionary.
"""
from app.models import Category, Routing, Team, Urgency
from app.triage.rules import RuleOutcome

TEAM_BY_CATEGORY = {
    Category.BUG: Team.ENGINEERING,
    Category.BILLING: Team.FINANCE,
    Category.ACCOUNT_ACCESS: Team.ACCOUNT_SUPPORT,
    Category.FEATURE_REQUEST: Team.PRODUCT,
    Category.OTHER: Team.GENERAL_SUPPORT,
}

# Service level: maximum time before the first answer
SLA_HOURS = {Urgency.HIGH: 4, Urgency.MEDIUM: 24, Urgency.LOW: 72}


def route(category: Category, outcome: RuleOutcome) -> Routing:
    if "security_incident" in outcome.rules_applied:
        team = Team.SECURITY            # security goes straight to the experts
    elif outcome.needs_human_review:
        team = Team.HUMAN_REVIEW        # the AI was unsure: a person decides
    else:
        team = TEAM_BY_CATEGORY[category]

    return Routing(
        team=team,
        final_urgency=outcome.final_urgency,
        sla_hours=SLA_HOURS[outcome.final_urgency],
        rules_applied=outcome.rules_applied,
        needs_human_review=outcome.needs_human_review,
    )