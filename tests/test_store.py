from app.models import Routing, Ticket, TriageResult
from app.store import SQLiteTicketStore


def make_ticket(subject="Charged twice") -> Ticket:
    return Ticket(customer_email="marie@client.fr", subject=subject,
                  body="My card was charged twice for October.")


def test_tickets_survive_a_restart(tmp_path):
    db_file = str(tmp_path / "tickets.db")
    ticket = SQLiteTicketStore(db_file).add(make_ticket())

    reopened = SQLiteTicketStore(db_file)  # like restarting the server
    assert reopened.get(ticket.id) == ticket


def test_triage_and_routing_round_trip(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    ticket = make_ticket()
    ticket.status = "routed"
    ticket.triage = TriageResult(category="billing", urgency="low", summary="Double charge",
                                 confidence=0.9, reason="Invoice", model="gemini",
                                 attempts=1, needs_human_review=False)
    ticket.routing = Routing(team="finance", final_urgency="medium", sla_hours=24,
                             rules_applied=["customer_marked_urgent"], needs_human_review=False)
    store.add(ticket)

    loaded = store.get(ticket.id)
    assert loaded == ticket                      # every field comes back identical
    assert loaded.routing.rules_applied == ["customer_marked_urgent"]


def test_add_twice_updates_instead_of_duplicating(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    ticket = store.add(make_ticket())
    ticket.status = "triaged"
    store.add(ticket)
    assert len(store.list()) == 1
    assert store.get(ticket.id).status == "triaged"


def test_list_newest_first_with_limit(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    first = store.add(make_ticket("First"))
    second = store.add(make_ticket("Second"))
    assert [t.id for t in store.list()] == [second.id, first.id]
    assert len(store.list(limit=1)) == 1


def test_unknown_id_returns_none(tmp_path):
    assert SQLiteTicketStore(str(tmp_path / "t.db")).get("nope") is None