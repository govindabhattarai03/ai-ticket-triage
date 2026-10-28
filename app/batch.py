"""Triage a whole file of tickets in one command, and store the results in SQLite.

Run:  python -m app.batch data/sample_tickets.jsonl
      python -m app.batch data/sample_tickets.jsonl --limit 5 --delay 4

Designed like a real data pipeline job:
- Idempotent: each ticket keeps its id from the file, and tickets already routed
  are skipped. Running the command twice never triages (or pays for) a ticket twice.
- Resumable: if the LLM stops answering (rate limit, quota, network), the job stops
  cleanly. Run the same command again and it continues where it stopped.
- Rate-limit friendly: waits a few seconds between LLM calls (free tiers are limited).
"""
import argparse
import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from app import config
from app.llm.base import LLMClient, LLMError
from app.llm.factory import get_llm
from app.models import Ticket
from app.store import SQLiteTicketStore
from app.triage.pipeline import triage_ticket


@dataclass
class BatchReport:
    processed: int = 0
    skipped: int = 0
    stopped_early: bool = False
    error: str = ""
    latencies: list[float] = field(default_factory=list)


def load_tickets(path: Path) -> list[Ticket]:
    """Read a JSONL file (one JSON object per line) into validated Ticket objects."""
    tickets = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), start=1):
        if not line.strip():
            continue
        row = json.loads(line)
        tickets.append(Ticket(id=row["id"], customer_email=row["customer_email"],
                              subject=row["subject"], body=row["body"]))
    return tickets


def run_batch(tickets: list[Ticket], store: SQLiteTicketStore, llm: LLMClient,
              delay: float = 0.0, sleep=time.sleep, log=print) -> BatchReport:
    report = BatchReport()
    for i, ticket in enumerate(tickets, start=1):
        existing = store.get(ticket.id)
        if existing is not None and existing.status == "routed":
            report.skipped += 1
            continue

        if report.processed > 0 and delay > 0:
            sleep(delay)

        start = time.perf_counter()
        try:
            ticket.triage, ticket.routing = triage_ticket(ticket, llm)
        except LLMError as e:
            report.stopped_early, report.error = True, str(e)
            log(f"[{i}/{len(tickets)}] {ticket.id} stopped: {e}")
            break
        elapsed = time.perf_counter() - start

        ticket.status = "routed"
        store.add(ticket)
        report.processed += 1
        report.latencies.append(elapsed)
        r = ticket.routing
        log(f"[{i}/{len(tickets)}] {ticket.id} {ticket.triage.category.value:<15} -> "
            f"{r.team.value:<15} {r.final_urgency.value:<6} SLA {r.sla_hours:>2}h  ({elapsed:.1f}s)")
    return report


def print_summary(report: BatchReport, store: SQLiteTicketStore) -> None:
    print("\n=== Batch summary ===")
    print(f"Triaged now: {report.processed}   Already done (skipped): {report.skipped}")
    if report.latencies:
        avg = sum(report.latencies) / len(report.latencies)
        print(f"Average time per ticket: {avg:.2f}s   Slowest: {max(report.latencies):.2f}s")
    print("\nAll tickets in the database:")
    for column in ("team", "final_urgency", "category"):
        print(f"  by {column:<14} {store.count_by(column)}")
    if report.stopped_early:
        print(f"\nStopped early: {report.error}")
        print("Run the same command again later: finished tickets will be skipped.")


def main() -> None:
    parser = argparse.ArgumentParser(description="Triage a JSONL file of tickets.")
    parser.add_argument("file", type=Path, help="JSONL file, e.g. data/sample_tickets.jsonl")
    parser.add_argument("--limit", type=int, help="only process the first N tickets")
    parser.add_argument("--delay", type=float, default=4.0,
                        help="seconds to wait between LLM calls (default 4, for free-tier limits)")
    parser.add_argument("--db", default=config.DATABASE_PATH, help="SQLite file (default from .env)")
    args = parser.parse_args()

    tickets = load_tickets(args.file)[: args.limit]
    store = SQLiteTicketStore(args.db)
    try:
        llm = get_llm()
    except LLMError as e:
        raise SystemExit(f"Cannot start: {e}")

    print(f"Triaging {len(tickets)} tickets from {args.file} with {llm.name} -> {args.db}\n")
    report = run_batch(tickets, store, llm, delay=args.delay)
    print_summary(report, store)


if __name__ == "__main__":
    main()