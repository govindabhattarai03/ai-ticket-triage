"""The full triage workflow: LLM -> business rules -> routing.

Each step is a separate, tested function. The pipeline only connects them,
so any step can be improved or replaced without touching the others.
"""
from app.llm.base import LLMClient
from app.models import Routing, TicketIn, TriageResult
from app.triage.classifier import classify_ticket
from app.triage.router import route
from app.triage.rules import apply_rules


def triage_ticket(ticket: TicketIn, llm: LLMClient) -> tuple[TriageResult, Routing]:
    triage = classify_ticket(ticket, llm)          # 1. understand the text (AI)
    outcome = apply_rules(ticket, triage)          # 2. apply company rules (code)
    routing = route(triage.category, outcome)      # 3. pick the team and SLA (lookup)
    return triage, routing