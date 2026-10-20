"""FastAPI service: the entry point where support tickets arrive.

Run:  uvicorn app.main:app --reload   then open http://localhost:8000/docs
"""
from fastapi import Depends, FastAPI, HTTPException, Query

from app.llm.base import LLMClient, LLMError
from app.llm.factory import get_llm
from app.models import Ticket, TicketIn
from app.store import InMemoryTicketStore
from app.triage.classifier import classify_ticket

app = FastAPI(
    title="AI Ticket Triage",
    version="0.2.0",
    description="Receives support tickets and classifies them with an LLM.",
)

store = InMemoryTicketStore()


@app.get("/health")
def health():
    return {"status": "ok"}


@app.post("/tickets", response_model=Ticket, status_code=201)
def create_ticket(ticket_in: TicketIn):
    """Receive a new ticket. Invalid input is rejected with HTTP 422 by Pydantic."""
    return store.add(Ticket(**ticket_in.model_dump()))


@app.get("/tickets", response_model=list[Ticket])
def list_tickets(limit: int = Query(50, ge=1, le=500)):
    return store.list(limit)


@app.get("/tickets/{ticket_id}", response_model=Ticket)
def get_ticket(ticket_id: str):
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    return ticket


def llm_dependency() -> LLMClient:
    """Give the endpoint an LLM client; a configuration problem becomes a clear 503."""
    try:
        return get_llm()
    except LLMError as e:
        raise HTTPException(status_code=503, detail=str(e))


@app.post("/tickets/{ticket_id}/classify", response_model=Ticket)
def classify(ticket_id: str, llm: LLMClient = Depends(llm_dependency)):
    """Ask the LLM to classify the ticket and store the result on it."""
    ticket = store.get(ticket_id)
    if ticket is None:
        raise HTTPException(status_code=404, detail="Ticket not found")
    try:
        ticket.triage = classify_ticket(ticket, llm)
    except LLMError as e:
        raise HTTPException(status_code=503, detail=f"LLM unavailable: {e}")
    ticket.status = "triaged"
    return store.add(ticket)
