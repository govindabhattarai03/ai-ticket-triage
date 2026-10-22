import json
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from app.main import app, store
from app.models import Category, TicketIn, Urgency

client = TestClient(app)

VALID_TICKET = {
    "customer_email": "marie@client.fr",
    "subject": "Invoice charged twice",
    "body": "My card was charged twice for the October invoice.",
}


@pytest.fixture(autouse=True)
def empty_store():
    store.clear()


def test_health():
    assert client.get("/health").json() == {"status": "ok"}


def test_create_and_fetch_ticket():
    created = client.post("/tickets", json=VALID_TICKET)
    assert created.status_code == 201
    ticket = created.json()
    assert ticket["status"] == "new"

    fetched = client.get(f"/tickets/{ticket['id']}")
    assert fetched.status_code == 200
    assert fetched.json()["subject"] == VALID_TICKET["subject"]


@pytest.mark.parametrize(
    "field, bad_value",
    [("customer_email", "not-an-email"), ("subject", "x"), ("body", "too short")],
)
def test_invalid_ticket_is_rejected(field, bad_value):
    response = client.post("/tickets", json={**VALID_TICKET, field: bad_value})
    assert response.status_code == 422


def test_unknown_ticket_returns_404():
    assert client.get("/tickets/does-not-exist").status_code == 404


def test_list_returns_newest_first():
    first = client.post("/tickets", json=VALID_TICKET).json()
    second = client.post("/tickets", json={**VALID_TICKET, "subject": "Second ticket"}).json()
    ids = [t["id"] for t in client.get("/tickets").json()]
    assert ids == [second["id"], first["id"]]


def test_sample_dataset_is_valid():
    path = Path(__file__).parent.parent / "data" / "sample_tickets.jsonl"
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines()]
    assert len(rows) == 50
    for row in rows:
        TicketIn(customer_email=row["customer_email"], subject=row["subject"], body=row["body"])
        Category(row["expected_category"])
        Urgency(row["expected_urgency"])


def test_classify_endpoint_stores_triage():
    from app.llm.fake import FakeLLM
    from app.main import llm_dependency

    app.dependency_overrides[llm_dependency] = lambda: FakeLLM(
        ['{"category": "billing", "urgency": "medium", "summary": "Charged twice", '
         '"confidence": 0.95, "reason": "Double charge"}']
    )
    try:
        ticket = client.post("/tickets", json=VALID_TICKET).json()
        response = client.post(f"/tickets/{ticket['id']}/classify")
        assert response.status_code == 200
        body = response.json()
        assert body["status"] == "triaged"
        assert body["triage"]["category"] == "billing"
        assert body["triage"]["urgency"] == "medium"
        assert client.post("/tickets/unknown/classify").status_code == 404
    finally:
        app.dependency_overrides.clear()