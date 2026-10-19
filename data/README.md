# Sample data

`sample_tickets.jsonl` holds 50 realistic support tickets (one JSON object per line), written for this project.
Each one is labelled with the correct answer:

- `expected_category`: bug, billing, account_access, feature_request or other
- `expected_urgency`: low, medium or high

About 1 in 5 tickets is in French, because a French company receives tickets in both languages.

The labels are the "ground truth" used in stage 5 to measure how accurate the LLM triage is.
