"""The full triage workflow: LLM -> business rules -> routing.

Each step is a separate, tested function. The pipeline only connects them,
so any step can be improved or replaced without touching the others.
"""
import time

from app.llm.base import LLMClient
from app.models import Routing, TicketIn, TriageMetrics, TriageResult
from app.triage.classifier import classify_ticket
from app.triage.router import route
from app.triage.rules import apply_rules


def triage_ticket(ticket: TicketIn, llm: LLMClient) -> tuple[TriageResult, Routing]:
    triage = classify_ticket(ticket, llm)          # 1. understand the text (AI)
    outcome = apply_rules(ticket, triage)          # 2. apply company rules (code)
    routing = route(triage.category, outcome)      # 3. pick the team and SLA (lookup)
    return triage, routing

def triage_with_metrics(ticket: TicketIn, llm: LLMClient
                        ) -> tuple[TriageResult, Routing, TriageMetrics]:
    """Same as triage_ticket, but also measures time, requests, rate limits and tokens."""
    before = llm.usage.snapshot()
    start = time.perf_counter()
    triage, routing = triage_ticket(ticket, llm)
    used = llm.usage.since(before)
    metrics = TriageMetrics(
        latency_ms=round((time.perf_counter() - start) * 1000),
        llm_requests=used.requests,
        rate_limited=used.rate_limited,
        input_tokens=used.input_tokens,
        output_tokens=used.output_tokens,
    )
    return triage, routing, metrics