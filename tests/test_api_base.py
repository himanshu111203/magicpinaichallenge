import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.main import app
from src.services.context_store import context_store
from src.services.conversation_store import conversation_store
from src.services.chat_service import ChatService

BASE_DIR = Path(__file__).resolve().parent.parent
EXPANDED_DIR = BASE_DIR / "expanded"


@pytest.fixture(autouse=True)
def clean_store():
    """Ensure request-scoped context and conversation state is clear before each test."""
    context_store.clear()
    conversation_store.clear()
    yield
    context_store.clear()
    conversation_store.clear()


@pytest.fixture
def client():
    """FastAPI TestClient fixture."""
    return TestClient(app)


def test_healthz_fresh_start(client):
    """GET /v1/healthz must report all-zero context counts on boot."""
    resp = client.get("/v1/healthz")
    assert resp.status_code == 200
    data = resp.json()

    assert data["status"] == "ok"
    assert "uptime_seconds" in data
    assert data["contexts_loaded"] == {
        "category": 0,
        "merchant": 0,
        "customer": 0,
        "trigger": 0,
    }


def test_metadata(client):
    """GET /v1/metadata must return team and model information."""
    resp = client.get("/v1/metadata")
    assert resp.status_code == 200
    data = resp.json()

    assert "team_name" in data
    assert "model" in data
    assert "approach" in data
    assert "version" in data
    assert "submitted_at" in data


def test_context_ingest_and_versioning(client):
    """Test POST /v1/context for success, stale version, and update."""
    cat_file = EXPANDED_DIR / "categories" / "dentists.json"
    with open(cat_file, encoding="utf-8") as f:
        payload = json.load(f)

    # 1. New context -> 200
    resp = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 1,
        "payload": payload,
        "delivered_at": "2026-04-26T10:00:00Z"
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["accepted"] is True
    assert data["ack_id"] == "ack_dentists_v1"

    # 2. Lower version -> 409
    resp_stale = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 0,
        "payload": payload,
    })
    assert resp_stale.status_code == 409
    data_stale = resp_stale.json()
    assert data_stale["accepted"] is False
    assert data_stale["reason"] == "stale_version"
    assert data_stale["current_version"] == 1

    # 3. Higher version -> 200
    resp_v2 = client.post("/v1/context", json={
        "scope": "category",
        "context_id": "dentists",
        "version": 2,
        "payload": payload,
    })
    assert resp_v2.status_code == 200
    assert resp_v2.json()["accepted"] is True
    assert resp_v2.json()["ack_id"] == "ack_dentists_v2"


def test_context_ingest_invalid_scope(client):
    """POST /v1/context with unknown scope returns 400."""
    resp = client.post("/v1/context", json={
        "scope": "unsupported_scope",
        "context_id": "test_id",
        "version": 1,
        "payload": {"foo": "bar"},
    })
    assert resp.status_code == 400
    assert resp.json()["accepted"] is False
    assert resp.json()["reason"] == "invalid_scope"


def test_context_ingest_walkin_customer(client):
    """Verify anonymous walk-in customer (c_015_anonymous_for_m010) ingests cleanly."""
    c15_file = EXPANDED_DIR / "customers" / "c_015_anonymous_for_m010.json"
    with open(c15_file, encoding="utf-8") as f:
        payload = json.load(f)

    resp = client.post("/v1/context", json={
        "scope": "customer",
        "context_id": "c_015_anonymous_for_m010",
        "version": 1,
        "payload": payload,
    })
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_context_ingest_placeholder_trigger(client):
    """Verify placeholder trigger ingests cleanly."""
    placeholder_file = None
    for p in (EXPANDED_DIR / "triggers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("payload", {}).get("placeholder") is True:
            placeholder_file = p
            break

    assert placeholder_file is not None, "Placeholder trigger file must exist in expanded/triggers"
    with open(placeholder_file, encoding="utf-8") as f:
        payload = json.load(f)

    resp = client.post("/v1/context", json={
        "scope": "trigger",
        "context_id": payload["id"],
        "version": 1,
        "payload": payload,
    })
    assert resp.status_code == 200
    assert resp.json()["accepted"] is True


def test_warmup_simulation_255_base_contexts(client):
    """
    Simulate the official competition Warmup phase (T-15min):
    Push 5 categories, 50 merchants, 200 customers (total 255 base contexts).
    Assert healthz updates accurately to reflect exactly all 255 contexts loaded.
    """
    # 1. Check healthz before warmup
    resp0 = client.get("/v1/healthz")
    assert resp0.status_code == 200
    assert resp0.json()["contexts_loaded"] == {"category": 0, "merchant": 0, "customer": 0, "trigger": 0}

    # 2. Push all 5 categories
    for p in (EXPANDED_DIR / "categories").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        resp = client.post("/v1/context", json={
            "scope": "category",
            "context_id": data["slug"],
            "version": 1,
            "payload": data,
        })
        assert resp.status_code == 200

    # 3. Push all 50 merchants
    for p in (EXPANDED_DIR / "merchants").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        resp = client.post("/v1/context", json={
            "scope": "merchant",
            "context_id": data["merchant_id"],
            "version": 1,
            "payload": data,
        })
        assert resp.status_code == 200

    # 4. Push all 200 customers
    for p in (EXPANDED_DIR / "customers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        resp = client.post("/v1/context", json={
            "scope": "customer",
            "context_id": data["customer_id"],
            "version": 1,
            "payload": data,
        })
        assert resp.status_code == 200

    # 5. Query healthz and verify counts
    resp_warmup = client.get("/v1/healthz")
    assert resp_warmup.status_code == 200
    counts = resp_warmup.json()["contexts_loaded"]
    assert counts == {
        "category": 5,
        "merchant": 50,
        "customer": 200,
        "trigger": 0,
    }


def test_tick_and_reply_stubs(client):
    """Verify initial endpoints for tick and reply respond with valid shapes."""
    tick_resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": ["trg_001"],
    })
    assert tick_resp.status_code == 200
    assert tick_resp.json() == {"actions": []}

    reply_resp = client.post("/v1/reply", json={
        "conversation_id": "conv_001",
        "merchant_id": "m_001",
        "message": "Hello",
        "received_at": "2026-04-26T10:01:00Z",
        "turn_number": 1,
    })
    assert reply_resp.status_code == 200
    assert reply_resp.json()["action"] in ("send", "wait", "end")

def test_chat_endpoint_grounded_and_clarify(client):
    """Verify POST /v1/chat handles grounded triggers, ungrounded queries, and inbound turns."""
    # 1. Grounded scenario in Dentists
    resp = client.post("/v1/chat", json={
        "category": "dentists",
        "message": "DCI radiograph compliance dose limits",
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    assert "Dental Council of India" in data["body"]
    assert "binary_yes_no" in data["cta"]
    assert len(data["grounding"]) > 0

    # 2. Ungrounded query rejection (zero-hallucination safeguard)
    resp_ungrounded = client.post("/v1/chat", json={
        "category": "dentists",
        "message": "tell me a joke about cats and dogs",
    })
    assert resp_ungrounded.status_code == 200
    data_ungrounded = resp_ungrounded.json()
    assert data_ungrounded["action"] == "clarify"
    assert "Rohini Dental Studio" in data_ungrounded["body"]
    assert len(data_ungrounded["grounding"]) > 0

    # 3. Inbound conversation turn
    resp_inbound = client.post("/v1/chat", json={
        "category": "dentists",
        "message": "Ok lets do it. Whats next?",
    })
    assert resp_inbound.status_code == 200
    data_inbound = resp_inbound.json()
    assert data_inbound["action"] == "send"


def test_chat_endpoint_differentiated_fallback_intents(client, monkeypatch):
    """Verify that greeting, business growth, and medical queries receive distinct, appropriate responses."""
    monkeypatch.setattr(
        ChatService,
        "_call_gemini_chat",
        classmethod(lambda cls, *args, **kwargs: pytest.fail("deterministic intent called Gemini")),
    )
    # A. Greeting / identity question
    resp_greeting = client.post("/v1/chat", json={
        "category": "pharmacies",
        "message": "hello are you from pharmacy",
    })
    assert resp_greeting.status_code == 200
    data_greeting = resp_greeting.json()
    assert data_greeting["action"] == "greet"
    assert "Vera" in data_greeting["body"]
    assert "Metro Care Pharmacy" in data_greeting["body"]

    # B. General business question
    resp_growth = client.post("/v1/chat", json={
        "category": "pharmacies",
        "message": "how i grow my pharmacy shop",
    })
    assert resp_growth.status_code == 200
    data_growth = resp_growth.json()
    assert data_growth["action"] == "bridge_growth"
    assert any(w in data_growth["body"].lower() for w in ["growth", "consulting", "telemetry", "operational"])
    assert "Metro Care Pharmacy" in data_growth["body"]
    assert "chronic_refill_cohort:64" in data_growth["body"]

    # C. Out-of-scope clinical/medical question
    resp_medical = client.post("/v1/chat", json={
        "category": "pharmacies",
        "message": "difference between paracetamol and dolo",
    })
    assert resp_medical.status_code == 200
    data_medical = resp_medical.json()
    assert data_medical["action"] == "decline_medical"
    assert any(w in data_medical["body"].lower() for w in ["medical", "clinical", "advice", "pharmacist", "doctor"])

    # All three must be visibly distinct and non-identical
    assert data_greeting["body"] != data_growth["body"]
    assert data_greeting["body"] != data_medical["body"]
    assert data_growth["body"] != data_medical["body"]


def test_dental_acceptance_composes_selected_context(client, monkeypatch):
    """Acceptance must compose the selected dental signal and active offer, not a mock confirmation."""
    monkeypatch.setattr(
        ChatService,
        "_call_gemini_chat",
        classmethod(lambda cls, *args, **kwargs: pytest.fail("deterministic intent called Gemini")),
    )
    messages = (
        "hi",
        "how can I grow my clinic?",
        "difference between paracetamol and dolo",
        "ok convert",
    )
    responses = [
        client.post("/v1/chat", json={
            "category": "dentists",
            "conversation_id": "conv_dental_grounded_acceptance",
            "turn": turn,
            "message": message,
        }).json()
        for turn, message in enumerate(messages, start=1)
    ]

    final = responses[-1]
    assert final["action"] == "send"
    assert final["cta"] == "binary_yes_no"
    assert "Rohini Dental Studio" in final["body"]
    assert "Rohini" in final["body"]
    assert "Dental Cleaning @ ₹299" in final["body"]
    assert "schedule a cleaning appointment" in final["body"]
    assert "google" not in final["body"].lower()
    assert "quality services" not in final["body"].lower()
    assert "verified appointments" not in final["body"].lower()

