"""Ticket storage.

Two implementations with the same methods (add, get, list, clear):
- InMemoryTicketStore: a dict, lost when the server restarts. Handy for quick experiments.
- SQLiteTicketStore: a real SQL database in one file, so tickets survive restarts
  and can be analysed with SQL.

The API only uses these four methods, so switching storage needed no change in the endpoints.
"""
import json
import sqlite3
import threading
from datetime import datetime, timezone

from app.models import Routing, Ticket, TriageResult


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


# One row per ticket. The LLM's answer and the final routing are stored in separate
# columns (llm_urgency vs final_urgency) so we can later measure where the rules changed things.
SCHEMA = """
CREATE TABLE IF NOT EXISTS tickets (
    id                  TEXT PRIMARY KEY,
    customer_email      TEXT NOT NULL,
    subject             TEXT NOT NULL,
    body                TEXT NOT NULL,
    received_at         TEXT NOT NULL,   -- ISO 8601, UTC
    status              TEXT NOT NULL,   -- new | triaged | routed

    -- what the LLM said
    category            TEXT,
    llm_urgency         TEXT,
    summary             TEXT,
    confidence          REAL,
    reason              TEXT,
    model               TEXT,
    attempts            INTEGER,
    llm_needs_review    INTEGER,         -- 0/1: SQLite has no boolean type

    -- final decision after business rules and routing
    team                TEXT,
    final_urgency       TEXT,
    sla_hours           INTEGER,
    rules_applied       TEXT,            -- JSON list, e.g. ["security_incident"]
    needs_human_review  INTEGER,

    updated_at          TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS idx_tickets_received_at ON tickets (received_at);
CREATE INDEX IF NOT EXISTS idx_tickets_team ON tickets (team);
"""

COLUMNS = [
    "id", "customer_email", "subject", "body", "received_at", "status",
    "category", "llm_urgency", "summary", "confidence", "reason", "model", "attempts",
    "llm_needs_review", "team", "final_urgency", "sla_hours", "rules_applied",
    "needs_human_review", "updated_at",
]


class SQLiteTicketStore:
    def __init__(self, path: str = "tickets.db") -> None:
        # One shared connection; FastAPI may call us from several threads, so a lock
        # makes sure only one thread uses the connection at a time.
        self._conn = sqlite3.connect(path, check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        self._lock = threading.Lock()
        with self._lock:
            self._conn.executescript(SCHEMA)

    # ---- Ticket <-> row conversion -------------------------------------------------
    @staticmethod
    def _to_row(ticket: Ticket) -> dict:
        t, r = ticket.triage, ticket.routing
        return {
            "id": ticket.id,
            "customer_email": ticket.customer_email,
            "subject": ticket.subject,
            "body": ticket.body,
            "received_at": ticket.received_at.isoformat(),
            "status": ticket.status,
            "category": t.category.value if t else None,
            "llm_urgency": t.urgency.value if t else None,
            "summary": t.summary if t else None,
            "confidence": t.confidence if t else None,
            "reason": t.reason if t else None,
            "model": t.model if t else None,
            "attempts": t.attempts if t else None,
            "llm_needs_review": int(t.needs_human_review) if t else None,
            "team": r.team.value if r else None,
            "final_urgency": r.final_urgency.value if r else None,
            "sla_hours": r.sla_hours if r else None,
            "rules_applied": json.dumps(r.rules_applied) if r else None,
            "needs_human_review": int(r.needs_human_review) if r else None,
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Ticket:
        triage = None
        if row["category"] is not None:
            triage = TriageResult(
                category=row["category"], urgency=row["llm_urgency"], summary=row["summary"],
                confidence=row["confidence"], reason=row["reason"], model=row["model"],
                attempts=row["attempts"], needs_human_review=bool(row["llm_needs_review"]),
            )
        routing = None
        if row["team"] is not None:
            routing = Routing(
                team=row["team"], final_urgency=row["final_urgency"], sla_hours=row["sla_hours"],
                rules_applied=json.loads(row["rules_applied"]),
                needs_human_review=bool(row["needs_human_review"]),
            )
        return Ticket(
            id=row["id"], customer_email=row["customer_email"], subject=row["subject"],
            body=row["body"], received_at=row["received_at"], status=row["status"],
            triage=triage, routing=routing,
        )

    # ---- the four methods the API uses ---------------------------------------------
    def add(self, ticket: Ticket) -> Ticket:
        """Insert a new ticket, or update it if the id already exists (an "upsert")."""
        placeholders = ", ".join(f":{c}" for c in COLUMNS)
        updates = ", ".join(f"{c} = excluded.{c}" for c in COLUMNS if c != "id")
        sql = (f"INSERT INTO tickets ({', '.join(COLUMNS)}) VALUES ({placeholders}) "
               f"ON CONFLICT(id) DO UPDATE SET {updates}")
        with self._lock, self._conn:   # "with conn" commits, or rolls back on error
            self._conn.execute(sql, self._to_row(ticket))
        return ticket

    def get(self, ticket_id: str) -> Ticket | None:
        with self._lock:
            row = self._conn.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,)).fetchone()
        return self._from_row(row) if row else None

    def list(self, limit: int = 50) -> list[Ticket]:
        with self._lock:
            rows = self._conn.execute(
                "SELECT * FROM tickets ORDER BY received_at DESC LIMIT ?", (limit,)
            ).fetchall()
        return [self._from_row(r) for r in rows]

    def clear(self) -> None:
        with self._lock, self._conn:
            self._conn.execute("DELETE FROM tickets")