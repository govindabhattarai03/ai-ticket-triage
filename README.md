# AI Ticket Triage

An internal tool that uses an LLM to automate how a company handles incoming support tickets:
classify each ticket, extract its key details, score its urgency, summarise it and route it to the right team.

> 🚧 Work in progress, built in stages. See the roadmap below.

## Roadmap

- [x] **Stage 1:** project setup, ticket data model, FastAPI service, labelled sample dataset, tests
- [ ] **Stage 2:** LLM client and ticket classification with validated JSON output
- [ ] **Stage 3:** orchestration: classify → extract → urgency → route, with business rules
- [ ] **Stage 4:** storage in SQL and batch automation
- [ ] **Stage 5:** evaluation: accuracy, latency and cost across models
- [ ] **Stage 6:** Docker, dashboard and final documentation

## Run it

```bash
python -m venv .venv
source .venv/bin/activate        # Windows: .venv\Scripts\activate
pip install -r requirements.txt
uvicorn app.main:app --reload    # then open http://localhost:8000/docs
pytest -q
```
