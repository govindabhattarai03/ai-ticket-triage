"""Business rules applied after the LLM.

The LLM is good at understanding text, but some decisions must be predictable
and easy to audit: a security incident must ALWAYS be treated as high urgency,
whatever the model says. These rules are plain Python, so they are fast, free,
always give the same result, and are easy to explain to a manager.

Every rule that fires adds its name to `rules_applied`, so we can always
explain why a ticket ended up with its final urgency.
"""
import re
import unicodedata
from dataclasses import dataclass, field

from app.models import Category, TicketIn, TriageResult, Urgency

# Patterns are written without accents: the ticket text is normalised the same way.
SECURITY_PATTERNS = [
    r"hack", r"suspicious login", r"phishing", r"data (breach|leak)", r"unauthori[sz]ed",
    r"pirat", r"connexion suspecte", r"fuite de donnees",
]
MASS_IMPACT_PATTERNS = [
    r"\ball (our |the )?(users|employees|customers|restaurants|staff|branches)",
    r"\bnone of our", r"\b(whole|entire) (team|company)", r"\beveryone",
    r"\btous (nos|les) (utilisateurs|salaries|clients|restaurants)", r"\baucun de nos",
    r"\btoute l'equipe",
    r"\b\d{2,} (users|employees|restaurants|people|customers|utilisateurs|salaries|clients)",
]
CUSTOMER_URGENT_PATTERNS = [
    r"\burgent", r"\basap\b", r"\bimmediately\b", r"\bright now\b", r"\burgence\b", r"\bau plus vite\b",
]

_LEVEL = {Urgency.LOW: 0, Urgency.MEDIUM: 1, Urgency.HIGH: 2}


@dataclass
class RuleOutcome:
    final_urgency: Urgency
    needs_human_review: bool
    rules_applied: list[str] = field(default_factory=list)


def normalize(text: str) -> str:
    """Lower-case and remove accents, so 'Sécurité' and 'securite' match the same pattern."""
    decomposed = unicodedata.normalize("NFKD", text)
    return "".join(c for c in decomposed if not unicodedata.combining(c)).lower()


def _matches(text: str, patterns: list[str]) -> bool:
    return any(re.search(p, text) for p in patterns)


def _at_least(current: Urgency, minimum: Urgency) -> Urgency:
    return current if _LEVEL[current] >= _LEVEL[minimum] else minimum


def apply_rules(ticket: TicketIn, triage: TriageResult) -> RuleOutcome:
    text = normalize(f"{ticket.subject} {ticket.body}")
    outcome = RuleOutcome(final_urgency=triage.urgency,
                          needs_human_review=triage.needs_human_review)
    security = _matches(text, SECURITY_PATTERNS)

    # 1. Security incidents are always high urgency, and a human must look at them.
    if security:
        outcome.final_urgency = Urgency.HIGH
        outcome.needs_human_review = True
        outcome.rules_applied.append("security_incident")

    # 2. When many people are blocked, it's high urgency.
    #    Not for feature requests: "useful for all our branches" is not an outage.
    if (_matches(text, MASS_IMPACT_PATTERNS) and outcome.final_urgency != Urgency.HIGH
            and triage.category != Category.FEATURE_REQUEST):
        outcome.final_urgency = Urgency.HIGH
        outcome.rules_applied.append("many_users_affected")

    # 3. If the customer says it's urgent, never leave it at low.
    #    (Not straight to high: customers write "urgent" on many small issues.)
    if _matches(text, CUSTOMER_URGENT_PATTERNS) and outcome.final_urgency == Urgency.LOW:
        outcome.final_urgency = _at_least(outcome.final_urgency, Urgency.MEDIUM)
        outcome.rules_applied.append("customer_marked_urgent")

    # 4. A feature request is never an emergency (unless it's about security).
    if (triage.category == Category.FEATURE_REQUEST and outcome.final_urgency == Urgency.HIGH
            and not security):
        outcome.final_urgency = Urgency.MEDIUM
        outcome.rules_applied.append("feature_request_capped")

    return outcome