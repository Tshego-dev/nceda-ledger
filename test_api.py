import os

# Must be set before `main` is imported: use an isolated in-memory database.
os.environ["DATABASE_URL"] = "sqlite://"

import pytest
from fastapi.testclient import TestClient
from sqlmodel import SQLModel

import main

VALID = {
    "customer_name": "Sipho Dlamini",
    "customer_id": "9001015000080",
    "customer_phone": "061 234 5678",
    "amount": 120.5,
    "items": "Bread, Milk",
}


@pytest.fixture()
def client():
    SQLModel.metadata.drop_all(main.engine)
    with TestClient(main.app) as c:  # lifespan creates the tables
        yield c


def test_health(client):
    assert client.get("/health").json() == {"status": "ok"}


def test_log_debt_and_read_ledger(client):
    r = client.post("/api/debts", json=VALID)
    assert r.status_code == 201
    rows = client.get("/api/ledger").json()
    assert len(rows) == 1
    row = rows[0]
    assert row["status"] == "PENDING"
    assert row["customer_phone"] == "0612345678"  # whitespace normalised
    assert row["amount"] == 120.5


def test_same_customer_reuses_profile(client):
    client.post("/api/debts", json=VALID)
    client.post("/api/debts", json={**VALID, "amount": 50})
    assert len(client.get("/api/ledger").json()) == 2


def test_id_name_mismatch_rejected_without_leaking_name(client):
    client.post("/api/debts", json=VALID)
    r = client.post("/api/debts", json={**VALID, "customer_name": "Someone Else"})
    assert r.status_code == 400
    assert "Sipho" not in r.text
    assert len(client.get("/api/ledger").json()) == 1


@pytest.mark.parametrize(
    "override",
    [
        {"customer_id": "123"},
        {"customer_id": "abcdefghijklm"},
        {"amount": 0},
        {"amount": -5},
        {"customer_phone": "abc"},
        {"customer_name": "   "},
        {"items": ""},
    ],
)
def test_invalid_payloads_rejected(client, override):
    r = client.post("/api/debts", json={**VALID, **override})
    assert r.status_code == 422


def test_status_flow_and_validation(client):
    debt_id = client.post("/api/debts", json=VALID).json()["debt_id"]

    assert client.patch(f"/api/debts/{debt_id}/status", params={"status": "ACTIVE"}).status_code == 200
    assert client.patch(f"/api/debts/{debt_id}/status", params={"status": "BOGUS"}).status_code == 422
    assert client.patch("/api/debts/9999/status", params={"status": "ACTIVE"}).status_code == 404

    assert client.patch(f"/api/debts/{debt_id}/status", params={"status": "SETTLED"}).status_code == 200
    # a settled debt cannot be reopened
    assert client.patch(f"/api/debts/{debt_id}/status", params={"status": "ACTIVE"}).status_code == 409


def test_ledger_filter_and_pagination(client):
    for i in range(3):
        client.post("/api/debts", json={**VALID, "amount": 10 + i})
    first = client.post("/api/debts", json=VALID).json()["debt_id"]
    client.patch(f"/api/debts/{first}/status", params={"status": "ACTIVE"})

    assert len(client.get("/api/ledger", params={"status": "ACTIVE"}).json()) == 1
    assert len(client.get("/api/ledger", params={"limit": 2}).json()) == 2
    assert client.get("/api/ledger", params={"status": "NOPE"}).status_code == 422
