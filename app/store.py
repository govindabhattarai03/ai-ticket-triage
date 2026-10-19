"""Ticket storage.

For now tickets live in memory (they disappear when the server restarts).
The API only talks to this small class, so in stage 4 it can be replaced by
a SQL database without changing the API code.
"""
from app.models import Ticket


class InMemoryTicketStore:
    def __init__(self) -> None:
        self._tickets: dict[str, Ticket] = {}

    def add(self, ticket: Ticket) -> Ticket:
        self._tickets[ticket.id] = ticket
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        return self._tickets.get(ticket_id)

    def list(self, limit: int = 50) -> list[Ticket]:
        newest_first = sorted(self._tickets.values(), key=lambda t: t.received_at, reverse=True)
        return newest_first[:limit]

    def clear(self) -> None:
        self._tickets.clear()
