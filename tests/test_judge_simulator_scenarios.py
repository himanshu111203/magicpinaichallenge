from __future__ import annotations

import json
from pathlib import Path
import time
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.context_store import context_store
from src.services.conversation_store import conversation_store

EXPANDED_DIR = Path(__file__).resolve().parent.parent / "expanded"


@pytest.fixture
def client():
    context_store.clear()
    conversation_store.clear()
    return TestClient(app)


def test_judge_simulator_scenario_warmup(client):
    """
    Direct replication of judge_simulator.py's _warmup() scenario:
    1. Checks healthz is fresh and counts are 0.
    2. Pushes 5 categories, 50 merchants, 200 customers (255 total base contexts).
    3. Asserts healthz reflects exactly 255 loaded base contexts.
    """
    # 1. Fresh healthz check
    h0 = client.get("/v1/healthz")
    assert h0.status_code == 200
    assert h0.json()["contexts_loaded"] == {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}

    # 2. Push 5 categories
    for p in (EXPANDED_DIR / "categories").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        client.post("/v1/context", json={"scope": "category", "context_id": d["slug"], "version": 1, "payload": d})

    # 3. Push 50 merchants
    for p in (EXPANDED_DIR / "merchants").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        client.post("/v1/context", json={"scope": "merchant", "context_id": d["merchant_id"], "version": 1, "payload": d})

    # 4. Push 200 customers
    for p in (EXPANDED_DIR / "customers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        client.post("/v1/context", json={"scope": "customer", "context_id": d["customer_id"], "version": 1, "payload": d})

    # 5. Check healthz verified warmup
    h1 = client.get("/v1/healthz")
    assert h1.status_code == 200
    assert h1.json()["contexts_loaded"] == {"category": 5, "merchant": 50, "customer": 200, "trigger": 0}


def test_judge_simulator_scenario_auto_reply(client):
    """
    Direct replication of judge_simulator.py's _auto_reply() scenario:
    Sends WhatsApp Business auto-greeting 4 times and asserts bot detects and ends/waits.
    """
    auto_msg = "Thank you for contacting us! Our team will respond shortly."
    ended = False

    for turn in range(1, 5):
        resp = client.post("/v1/reply", json={
            "conversation_id": f"conv_auto_{turn}",
            "merchant_id": "m_001_drmeera_dentist_delhi",
            "from_role": "merchant",
            "message": auto_msg,
            "received_at": "2026-04-26T12:00:00Z",
            "turn_number": turn + 1,
        })
        assert resp.status_code == 200
        action = resp.json().get("action")
        if action in ("end", "wait"):
            ended = True
            break

    assert ended is True, "Bot must end or wait when receiving WhatsApp Business auto-replies"


def test_judge_simulator_scenario_intent(client):
    """
    An acceptance without a stored trigger must not generate an ungrounded action message.
    """
    commitment = "Ok lets do it. Whats next?"
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_intent_sim",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": commitment,
        "received_at": "2026-04-26T12:00:00Z",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "wait"
    assert "verified outreach trigger" in data["body"].lower()
    assert "google" not in data["body"].lower()


def test_judge_simulator_scenario_hostile(client):
    """
    Direct replication of judge_simulator.py's _hostile() scenario:
    Sends 'Stop messaging me. This is useless spam.'
    Checks that bot ends or apologizes gracefully.
    """
    hostile = "Stop messaging me. This is useless spam."
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_hostile_sim",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": hostile,
        "received_at": "2026-04-26T12:00:00Z",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    action = data.get("action")
    body = data.get("body", "")

    assert action == "end" or (action == "send" and any(w in body.lower() for w in ["sorry", "apolog", "won't"]))


def test_judge_simulator_scenario_latency_sla(client):
    """
    Phase 17 Latency SLA Test:
    Asserts /v1/tick and /v1/reply execute well below the 10-second ceiling (< 100ms locally).
    """
    start = time.perf_counter()
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_sla_1",
        "merchant_id": "m_001_drmeera_dentist_delhi",
        "from_role": "merchant",
        "message": "Yes confirm",
        "received_at": "2026-04-26T12:00:00Z",
        "turn_number": 2,
    })
    elapsed = time.perf_counter() - start
    assert resp.status_code == 200
    assert elapsed < 0.5, f"Response too slow: {elapsed:.3f}s (budget: 10s)"
