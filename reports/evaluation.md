# Evaluation report
 
Model: `gemini-3.5-flash-lite` · Tickets evaluated: **50** · Generated: 2026-10-30

 
## Summary
 
| Metric | Result |
|---|---|
| Category accuracy | **100%** |
| Urgency accuracy, LLM alone | 88% |
| Urgency accuracy, after business rules | **88%** |
| Serious urgency errors (high ↔ low) | 0 |
| Urgency changed by the rules | 0 (fixed 0, broke 0) |
| Sent to human review | 1 |
| Category accuracy when confidence ≥ 0.8 | 100% (50 tickets) |
| Category accuracy when confidence < 0.8 | – (0 tickets) |
 
## Category confusion matrix
 
| expected ↓ / predicted → | bug | billing | account_access | feature_request | other |
|---|---|---|---|---|---|
| bug | **13** | · | · | · | · |
| billing | · | **11** | · | · | · |
| account_access | · | · | **10** | · | · |
| feature_request | · | · | · | **9** | · |
| other | · | · | · | · | **7** |
 
## Urgency confusion matrix (after rules)
 
| expected ↓ / predicted → | low | medium | high |
|---|---|---|---|
| low | **20** | · | · |
| medium | 3 | **13** | 3 |
| high | · | · | **11** |
 
## Tickets with at least one error
 
| Ticket | Subject | Expected | Got | Rules applied |
|---|---|---|---|---|
| T001 | App crashes when exporting report | bug / medium | bug / high | – |
| T012 | Mot de passe oublié, lien expiré | account_access / medium | account_access / high | – |
| T027 | Bulk import from Excel | feature_request / medium | feature_request / low | – |
| T029 | Mobile app freezes on Android 15 | bug / medium | bug / high | – |
| T030 | GDPR data request | other / medium | other / low | – |
| T038 | API rate limit too low | feature_request / medium | feature_request / low | – |
