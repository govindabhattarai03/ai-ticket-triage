# Model comparison

Generated: 2026-11-05. Same labelled tickets, same prompt, same business rules; only the model changes.

| Metric | `gemini-3.5-flash-lite` |
|---|---|
| Category accuracy | 100% |
| Urgency accuracy (after rules) | 88% |
| Serious urgency errors (high ↔ low) | 0 |
| Median time per ticket | 21.7s |
| 95th percentile time | 55.2s |
| Slowest ticket | 61.4s |
| Extra LLM requests (invalid JSON retried) | 0 |
| Rate-limited answers (429) waited out | 0 |
| Tokens per ticket | 383 |
| Estimated cost per 1,000 tickets (paid tier) | $0.24 |

- `gemini-3.5-flash-lite`: 50 tickets evaluated from `runs/flash-lite.db`

Times include retries and waits after rate limits (free tier). Costs are estimates from
published paid-tier prices; see `PRICES_PER_MILLION` in `app/compare.py`.
