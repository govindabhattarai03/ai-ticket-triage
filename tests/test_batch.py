from pathlib import Path

from app.batch import load_tickets, run_batch
from app.llm.base import LLMError
from app.llm.fake import FakeLLM
from app.store import SQLiteTicketStore

DATASET = Path(__file__).parent.parent / "data" / "sample_tickets.jsonl"


class FailingAfter(FakeLLM):
    """A fake LLM that stops answering after N calls, like hitting a rate limit."""

    def __init__(self, n_ok: int):
        super().__init__()
        self.n_ok = n_ok

    def complete(self, system: str, user: str) -> str:
        if self.calls >= self.n_ok:
            raise LLMError("HTTP 429: quota exceeded")
        return super().complete(system, user)


def quiet(*args):
    pass


def test_load_tickets_keeps_ids_from_the_file():
    tickets = load_tickets(DATASET)
    assert len(tickets) == 50
    assert tickets[0].id == "T001"


def test_batch_triages_and_stores_every_ticket(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    report = run_batch(load_tickets(DATASET), store, FakeLLM(), log=quiet)

    assert report.processed == 50
    assert len(store.list(limit=100)) == 50
    assert all(t.status == "routed" for t in store.list(limit=100))
    assert sum(store.count_by("team").values()) == 50


def test_running_twice_skips_finished_tickets(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    run_batch(load_tickets(DATASET), store, FakeLLM(), log=quiet)

    llm = FakeLLM()
    report = run_batch(load_tickets(DATASET), store, llm, log=quiet)
    assert report.skipped == 50
    assert llm.calls == 0          # no LLM call, no cost


def test_stops_cleanly_on_llm_error_and_resumes_later(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    tickets = load_tickets(DATASET)

    first = run_batch(tickets, store, FailingAfter(n_ok=10), log=quiet)
    assert first.processed == 10
    assert first.stopped_early and "429" in first.error

    second = run_batch(load_tickets(DATASET), store, FakeLLM(), log=quiet)
    assert second.skipped == 10
    assert second.processed == 40
    assert len(store.list(limit=100)) == 50


def test_waits_between_llm_calls(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    waits = []
    run_batch(load_tickets(DATASET)[:3], store, FakeLLM(), delay=4, sleep=waits.append, log=quiet)
    assert waits == [4, 4]          # between calls, not before the first one


def test_count_by_rejects_unknown_columns(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    try:
        store.count_by("id; DROP TABLE tickets")
    except ValueError:
        return
    raise AssertionError("SQL injection attempt was not blocked")