import json
import sqlite3
from pathlib import Path

import httpx
import pytest

from app import config
from app.batch import load_tickets, run_batch
from app.compare import cost_per_1000, summarise_run, to_markdown
from app.llm.factory import get_llm
from app.llm.fake import FakeLLM
from app.llm.openai_compat import OpenAICompatibleClient
from app.models import TicketIn
from app.store import SQLiteTicketStore
from app.triage.pipeline import triage_with_metrics
from tests.test_llm_client import use_fake_server

DATASET = Path(__file__).parent.parent / "data" / "sample_tickets.jsonl"
GOOD = json.dumps({"category": "bug", "urgency": "medium", "summary": "Export crashes",
                   "confidence": 0.9, "reason": "Crash"})


def test_client_counts_rate_limits_and_tokens(monkeypatch):
    answer = httpx.Response(200, json={"choices": [{"message": {"content": "hi"}}],
                                       "usage": {"prompt_tokens": 120, "completion_tokens": 30}})
    use_fake_server(monkeypatch, [httpx.Response(429), answer])
    client = OpenAICompatibleClient("https://example.com/v1", "m")

    client.complete("s", "u")

    assert client.usage.requests == 1
    assert client.usage.http_attempts == 2
    assert client.usage.rate_limited == 1
    assert (client.usage.input_tokens, client.usage.output_tokens) == (120, 30)


def test_metrics_count_json_retries_for_one_ticket():
    ticket = TicketIn(customer_email="a@b.fr", subject="Export crash",
                      body="The app crashes when I export to PDF.")
    llm = FakeLLM(["not json", GOOD])

    _, _, metrics = triage_with_metrics(ticket, llm)

    assert metrics.llm_requests == 2
    assert metrics.rate_limited == 0
    assert metrics.input_tokens > 0 and metrics.latency_ms >= 0


def test_migration_adds_new_columns_and_keeps_old_rows(tmp_path):
    """A database created before stage 5 (without the metric columns) still opens fine."""
    db = str(tmp_path / "old.db")
    conn = sqlite3.connect(db)
    conn.execute("""CREATE TABLE tickets (id TEXT PRIMARY KEY, customer_email TEXT NOT NULL,
        subject TEXT NOT NULL, body TEXT NOT NULL, received_at TEXT NOT NULL, status TEXT NOT NULL,
        category TEXT, llm_urgency TEXT, summary TEXT, confidence REAL, reason TEXT, model TEXT,
        attempts INTEGER, llm_needs_review INTEGER, team TEXT, final_urgency TEXT, sla_hours INTEGER,
        rules_applied TEXT, needs_human_review INTEGER, updated_at TEXT NOT NULL)""")
    conn.execute("""INSERT INTO tickets (id, customer_email, subject, body, received_at, status, updated_at)
        VALUES ('OLD1', 'a@b.fr', 'Old ticket', 'Created before the migration', '2026-10-01T10:00:00+00:00',
                'new', '2026-10-01T10:00:00+00:00')""")
    conn.commit()
    conn.close()

    store = SQLiteTicketStore(db)

    columns = {r[1] for r in sqlite3.connect(db).execute("PRAGMA table_info(tickets)")}
    assert {"latency_ms", "llm_requests", "rate_limited", "input_tokens", "output_tokens"} <= columns
    old = store.get("OLD1")
    assert old.subject == "Old ticket" and old.metrics is None


def test_metrics_round_trip_through_the_database(tmp_path):
    store = SQLiteTicketStore(str(tmp_path / "t.db"))
    run_batch(load_tickets(DATASET)[:3], store, FakeLLM(), log=lambda *a: None)
    ticket = store.get("T001")
    assert ticket.metrics is not None
    assert ticket.metrics.llm_requests == 1


def test_cost_estimate_uses_token_prices():
    # 1,000,000 input + 100,000 output tokens over 1,000 tickets with flash-lite ($0.30 / $2.50)
    assert cost_per_1000("gemini-3.5-flash-lite", 1_000_000, 100_000, 1000) == pytest.approx(0.55)
    assert cost_per_1000("unknown-model", 1000, 1000, 10) is None


def test_compare_two_runs_side_by_side(tmp_path):
    for name in ("a", "b"):
        store = SQLiteTicketStore(str(tmp_path / f"{name}.db"))
        run_batch(load_tickets(DATASET)[:10], store, FakeLLM(), log=lambda *a: None)

    runs = [summarise_run(DATASET, str(tmp_path / f"{n}.db")) for n in ("a", "b")]
    report = to_markdown(runs)

    assert runs[0]["n"] == 10 and runs[0]["missing"] == 40
    assert "Median time per ticket" in report and "Category accuracy" in report
    assert "| Metric | `fake` | `fake` |" in report


def test_factory_model_override(monkeypatch):
    monkeypatch.setattr(config, "LLM_PROVIDER", "gemini")
    monkeypatch.setattr(config, "GEMINI_API_KEY", "test-key")
    assert get_llm().name == config.GEMINI_MODEL
    assert get_llm("gemini-3.8-flash").name == "gemini-3.8-flash"


def test_report_warns_when_runs_cover_different_tickets(tmp_path):
    full, partial = SQLiteTicketStore(str(tmp_path / "full.db")), SQLiteTicketStore(str(tmp_path / "part.db"))
    run_batch(load_tickets(DATASET), full, FakeLLM(), log=lambda *a: None)
    run_batch(load_tickets(DATASET)[:5], partial, FakeLLM(), log=lambda *a: None)
    runs = [summarise_run(DATASET, str(tmp_path / n)) for n in ("full.db", "part.db")]
    assert "not a fair comparison" in to_markdown(runs)