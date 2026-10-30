import argparse
import json
from collections import Counter
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
 
from app import config
from app.models import Category, Urgency
from app.store import SQLiteTicketStore
 
CATEGORIES = [c.value for c in Category]
URGENCIES = [u.value for u in Urgency]
_LEVEL = {"low": 0, "medium": 1, "high": 2}
 
 
@dataclass
class EvalRow:
    id: str
    subject: str
    expected_category: str
    expected_urgency: str
    category: str
    llm_urgency: str
    final_urgency: str
    confidence: float
    rules_applied: list[str]
    needs_human_review: bool
 
 
def load_rows(dataset: Path, store: SQLiteTicketStore) -> tuple[list[EvalRow], list[str]]:
    """Join the labels with the stored results. Returns (rows, ids not triaged yet)."""
    rows, missing = [], []
    for line in dataset.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        label = json.loads(line)
        ticket = store.get(label["id"])
        if ticket is None or ticket.routing is None:
            missing.append(label["id"])
            continue
        rows.append(EvalRow(
            id=label["id"], subject=label["subject"],
            expected_category=label["expected_category"],
            expected_urgency=label["expected_urgency"],
            category=ticket.triage.category.value,
            llm_urgency=ticket.triage.urgency.value,
            final_urgency=ticket.routing.final_urgency.value,
            confidence=ticket.triage.confidence,
            rules_applied=ticket.routing.rules_applied,
            needs_human_review=ticket.routing.needs_human_review,
        ))
    return rows, missing
 
 
# ---- metrics (pure functions, easy to test) ------------------------------------------
def accuracy(pairs: list[tuple[str, str]]) -> float:
    """pairs = [(expected, predicted), ...] -> share of exact matches (0.0 to 1.0)."""
    return sum(e == p for e, p in pairs) / len(pairs) if pairs else 0.0
 
 
def confusion(pairs: list[tuple[str, str]], labels: list[str]) -> dict[str, dict[str, int]]:
    """matrix[expected][predicted] = number of tickets."""
    counts = Counter(pairs)
    return {e: {p: counts[(e, p)] for p in labels} for e in labels}
 
 
def serious_errors(pairs: list[tuple[str, str]]) -> int:
    """Urgency off by two levels (low <-> high): the mistakes that really hurt."""
    return sum(abs(_LEVEL[e] - _LEVEL[p]) == 2 for e, p in pairs)
 
 
def compute(rows: list[EvalRow]) -> dict:
    cat = [(r.expected_category, r.category) for r in rows]
    llm_urg = [(r.expected_urgency, r.llm_urgency) for r in rows]
    final_urg = [(r.expected_urgency, r.final_urgency) for r in rows]
    confident = [r for r in rows if r.confidence >= 0.8]
    unsure = [r for r in rows if r.confidence < 0.8]
    return {
        "n": len(rows),
        "category_accuracy": accuracy(cat),
        "llm_urgency_accuracy": accuracy(llm_urg),
        "final_urgency_accuracy": accuracy(final_urg),
        "serious_urgency_errors": serious_errors(final_urg),
        "rules_changed_urgency": sum(r.llm_urgency != r.final_urgency for r in rows),
        "rules_fixed": sum(r.llm_urgency != r.expected_urgency == r.final_urgency for r in rows),
        "rules_broke": sum(r.llm_urgency == r.expected_urgency != r.final_urgency for r in rows),
        "human_review": sum(r.needs_human_review for r in rows),
        "confident_n": len(confident),
        "confident_accuracy": accuracy([(r.expected_category, r.category) for r in confident]),
        "unsure_n": len(unsure),
        "unsure_accuracy": accuracy([(r.expected_category, r.category) for r in unsure]),
        "category_confusion": confusion(cat, CATEGORIES),
        "urgency_confusion": confusion(final_urg, URGENCIES),
    }
 
 
# ---- report ---------------------------------------------------------------------------
def _pct(x: float) -> str:
    return f"{x * 100:.0f}%"
 
 
def _matrix_md(matrix: dict[str, dict[str, int]]) -> str:
    labels = list(matrix)
    lines = ["| expected ↓ / predicted → | " + " | ".join(labels) + " |",
             "|---|" + "---|" * len(labels)]
    for e in labels:
        cells = [f"**{matrix[e][p]}**" if e == p and matrix[e][p] else str(matrix[e][p] or "·")
                 for p in labels]
        lines.append(f"| {e} | " + " | ".join(cells) + " |")
    return "\n".join(lines)
 
 
def to_markdown(m: dict, rows: list[EvalRow], missing: list[str], model: str) -> str:
    wrong = [r for r in rows
             if r.category != r.expected_category or r.final_urgency != r.expected_urgency]
    errors = "\n".join(
        f"| {r.id} | {r.subject} | {r.expected_category} / {r.expected_urgency} | "
        f"{r.category} / {r.final_urgency} | {', '.join(r.rules_applied) or '–'} |"
        for r in wrong) or "| – | no errors | | | |"
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    return f"""# Evaluation report
 
Model: `{model}` · Tickets evaluated: **{m['n']}** · Generated: {date}
{f"Not triaged yet (excluded): {', '.join(missing)}" if missing else ""}
 
## Summary
 
| Metric | Result |
|---|---|
| Category accuracy | **{_pct(m['category_accuracy'])}** |
| Urgency accuracy, LLM alone | {_pct(m['llm_urgency_accuracy'])} |
| Urgency accuracy, after business rules | **{_pct(m['final_urgency_accuracy'])}** |
| Serious urgency errors (high ↔ low) | {m['serious_urgency_errors']} |
| Urgency changed by the rules | {m['rules_changed_urgency']} (fixed {m['rules_fixed']}, broke {m['rules_broke']}) |
| Sent to human review | {m['human_review']} |
| Category accuracy when confidence ≥ 0.8 | {_pct(m['confident_accuracy']) if m['confident_n'] else '–'} ({m['confident_n']} tickets) |
| Category accuracy when confidence < 0.8 | {_pct(m['unsure_accuracy']) if m['unsure_n'] else '–'} ({m['unsure_n']} tickets) |
 
## Category confusion matrix
 
{_matrix_md(m['category_confusion'])}
 
## Urgency confusion matrix (after rules)
 
{_matrix_md(m['urgency_confusion'])}
 
## Tickets with at least one error
 
| Ticket | Subject | Expected | Got | Rules applied |
|---|---|---|---|---|
{errors}
"""
 
 
def main() -> None:
    parser = argparse.ArgumentParser(description="Compare triage results with the labels.")
    parser.add_argument("dataset", type=Path, help="labelled JSONL, e.g. data/sample_tickets.jsonl")
    parser.add_argument("--db", default=config.DATABASE_PATH)
    parser.add_argument("--out", type=Path, default=Path("reports/evaluation.md"))
    args = parser.parse_args()
 
    store = SQLiteTicketStore(args.db)
    rows, missing = load_rows(args.dataset, store)
    if not rows:
        raise SystemExit("No triaged tickets found. Run the batch job first: "
                         f"python -m app.batch {args.dataset}")
 
    m = compute(rows)
    model = ", ".join(sorted({store.get(r.id).triage.model for r in rows}))
    print(f"Evaluated {m['n']} tickets (model: {model})")
    print(f"  Category accuracy:               {_pct(m['category_accuracy'])}")
    print(f"  Urgency accuracy (LLM alone):    {_pct(m['llm_urgency_accuracy'])}")
    print(f"  Urgency accuracy (after rules):  {_pct(m['final_urgency_accuracy'])}")
    print(f"  Serious urgency errors:          {m['serious_urgency_errors']}")
    print(f"  Rules changed urgency:           {m['rules_changed_urgency']} "
          f"(fixed {m['rules_fixed']}, broke {m['rules_broke']})")
    if missing:
        print(f"  Not triaged yet: {len(missing)} ticket(s)")
 
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(to_markdown(m, rows, missing, model), encoding="utf-8")
    print(f"\nFull report: {args.out}")
 
 
if __name__ == "__main__":
    main()