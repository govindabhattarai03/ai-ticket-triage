"""Compare models side by side: accuracy, speed, retries, tokens and cost.

1. Run the batch job once per model, each into its own database:
     python -m app.batch data/sample_tickets.jsonl --model gemini-3.5-flash-lite --db runs/flash-lite.db
     python -m app.batch data/sample_tickets.jsonl --model gemini-3.8-flash      --db runs/flash.db
2. Compare them:
     python -m app.compare data/sample_tickets.jsonl runs/flash-lite.db runs/flash.db

Writes reports/model_comparison.md.
"""
import argparse
import statistics
from datetime import datetime, timezone
from pathlib import Path

from app.evaluate import compute, load_rows
from app.store import SQLiteTicketStore

# Paid-tier prices in US dollars per 1 million tokens: (input, output).
# Source: published Gemini API prices as of September 2026. Prices change, so check
# https://ai.google.dev/gemini-api/docs/pricing before relying on these numbers.
# On the free tier the real cost is 0; these estimate what a company would pay.
PRICES_PER_MILLION = {
    "gemini-3.5-flash-lite": (0.30, 2.50),
    "gemini-3.8-flash": (0.75, 3.75),
    "gemini-3.6-flash": (0.75, 3.75),
}


def summarise_run(dataset: Path, db: str) -> dict:
    store = SQLiteTicketStore(db)
    rows, missing = load_rows(dataset, store)
    if not rows:
        raise SystemExit(f"No triaged tickets in {db}. Run the batch job for it first.")
    quality = compute(rows)
    tickets = [store.get(r.id) for r in rows]
    measured = [t.metrics for t in tickets if t.metrics is not None]
    models = sorted({t.triage.model for t in tickets})

    summary = {"db": db, "model": ", ".join(models), "n": len(rows), "missing": len(missing),
               **quality, "measured": len(measured)}
    if measured:
        latencies = sorted(m.latency_ms for m in measured)
        input_tokens = sum(m.input_tokens for m in measured)
        output_tokens = sum(m.output_tokens for m in measured)
        summary.update({
            "median_s": statistics.median(latencies) / 1000,
            "p95_s": latencies[max(0, round(0.95 * len(latencies)) - 1)] / 1000,
            "max_s": latencies[-1] / 1000,
            "extra_requests": sum(m.llm_requests - 1 for m in measured),
            "rate_limited": sum(m.rate_limited for m in measured),
            "tokens_per_ticket": (input_tokens + output_tokens) / len(measured),
            "cost_per_1000": cost_per_1000(models[0], input_tokens, output_tokens, len(measured))
            if len(models) == 1 else None,
        })
    return summary


def cost_per_1000(model: str, input_tokens: int, output_tokens: int, n: int) -> float | None:
    """Estimated paid-tier cost (USD) of triaging 1,000 tickets with this model."""
    if model not in PRICES_PER_MILLION or n == 0:
        return None
    price_in, price_out = PRICES_PER_MILLION[model]
    per_ticket = (input_tokens * price_in + output_tokens * price_out) / 1_000_000 / n
    return per_ticket * 1000


def _fmt(value, kind: str) -> str:
    if value is None:
        return "–"
    return {"pct": f"{value * 100:.0f}%", "s": f"{value:.1f}s", "int": f"{value:.0f}",
            "usd": f"${value:.2f}"}[kind]


ROWS = [
    ("Category accuracy", "category_accuracy", "pct"),
    ("Urgency accuracy (after rules)", "final_urgency_accuracy", "pct"),
    ("Serious urgency errors (high ↔ low)", "serious_urgency_errors", "int"),
    ("Median time per ticket", "median_s", "s"),
    ("95th percentile time", "p95_s", "s"),
    ("Slowest ticket", "max_s", "s"),
    ("Extra LLM requests (invalid JSON retried)", "extra_requests", "int"),
    ("Rate-limited answers (429) waited out", "rate_limited", "int"),
    ("Tokens per ticket", "tokens_per_ticket", "int"),
    ("Estimated cost per 1,000 tickets (paid tier)", "cost_per_1000", "usd"),
]


def to_markdown(runs: list[dict]) -> str:
    header = "| Metric | " + " | ".join(f"`{r['model']}`" for r in runs) + " |"
    lines = [header, "|---|" + "---|" * len(runs)]
    for label, key, kind in ROWS:
        lines.append(f"| {label} | " + " | ".join(_fmt(r.get(key), kind) for r in runs) + " |")
    date = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    warning = ""
    if len({r["n"] for r in runs}) > 1:
        warning = ("\n> ⚠️ The runs cover different numbers of tickets, so this is not a fair "
                   "comparison yet. Finish every batch run first.\n")
    notes = "\n".join(f"- `{r['model']}`: {r['n']} tickets evaluated from `{r['db']}`"
                      + (f", {r['missing']} not triaged" if r["missing"] else "")
                      + (f", timing measured on {r['measured']}" if r["measured"] != r["n"] else "")
                      for r in runs)
    return f"""# Model comparison

Generated: {date}. Same labelled tickets, same prompt, same business rules; only the model changes.
{warning}
{chr(10).join(lines)}

{notes}

Times include retries and waits after rate limits (free tier). Costs are estimates from
published paid-tier prices; see `PRICES_PER_MILLION` in `app/compare.py`.
"""


def main() -> None:
    parser = argparse.ArgumentParser(description="Compare model runs side by side.")
    parser.add_argument("dataset", type=Path)
    parser.add_argument("dbs", nargs="+", help="one SQLite file per model run")
    parser.add_argument("--out", type=Path, default=Path("reports/model_comparison.md"))
    args = parser.parse_args()

    runs = [summarise_run(args.dataset, db) for db in args.dbs]
    report = to_markdown(runs)
    print(report)
    args.out.parent.mkdir(parents=True, exist_ok=True)
    args.out.write_text(report, encoding="utf-8")
    print(f"Saved to {args.out}")


if __name__ == "__main__":
    main()