"""FastAPI service: the entry point where support tickets arrive.

Run:  uvicorn app.main:app --reload   then open http://localhost:8000/docs
"""
from fastapi import FastAPI, HTTPException, Query

from app.models import Ticket, TicketIn
from app.store import InMemoryTicketStore

app = FastAPI(
    title="AI Ticket Triage",
    version="0.1.0",
    description="Receives support tickets; LLM triage is added in stage 2.",
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
