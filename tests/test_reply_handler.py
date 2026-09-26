from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from src.engine.reply_handler import ReplyHandler
from src.main import app
from src.services.conversation_store import conversation_store


@pytest.fixture(autouse=True)
def reset_conversations():
    conversation_store.clear()
    yield
    conversation_store.clear()


@pytest.fixture
def client():
    return TestClient(app)


def test_reply_auto_reply_pattern_detected():
    """Verify WhatsApp Business canned greetings are detected and ended."""
    auto_msg = "Thank you for contacting us! Our team will respond shortly."
    res = ReplyHandler.handle_reply(
        conversation_id="conv_auto_1",
        merchant_id="m_001",
        customer_id=None,
        from_role="merchant",
        message=auto_msg,
        received_at="2026-04-26T12:00:00Z",
        turn_number=2,
    )
    assert res["action"] in ("end", "wait")
    assert "auto-reply" in res["rationale"].lower() or "canned" in res["rationale"].lower()


def test_reply_intent_transition_switches_to_action_mode():
    """
    CRITICAL INTENT TEST (simulating judge simulator _intent check):
    When merchant commits ('Ok lets do it. Whats next?'):
    1. Must return action: 'send'
    2. Must contain action words: 'done', 'sending', 'draft', 'here', 'confirm', 'proceed', 'next'
    3. Must NOT contain qualifying words: 'would you', 'do you', 'can you tell', 'what if', 'how about'
    """
    commitment = "Ok lets do it. Whats next?"
    res = ReplyHandler.handle_reply(
        conversation_id="conv_intent_1",
        merchant_id="m_001",
        customer_id=None,
        from_role="merchant",
        message=commitment,
        received_at="2026-04-26T12:00:00Z",
        turn_number=2,
    )

    assert res["action"] == "send"
    body = res["body"].lower()

    actioning = ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
    qualifying = ["would you", "do you", "can you tell", "what if", "how about"]

    assert any(w in body for w in actioning), f"Expected action words in body: {body}"
    assert not any(w in body for w in qualifying), f"Qualifying words forbidden in action mode: {body}"


def test_reply_hostile_message_ends_cleanly():
    """Verify hostile/opt-out message ends conversation per judge simulator _hostile check."""
    hostile = "Stop messaging me. This is useless spam."
    res = ReplyHandler.handle_reply(
        conversation_id="conv_hostile_1",
        merchant_id="m_001",
        customer_id=None,
        from_role="merchant",
        message=hostile,
        received_at="2026-04-26T12:00:00Z",
        turn_number=2,
    )
    assert res["action"] == "end"
    assert "opt-out" in res["rationale"].lower() or "preference" in res["rationale"].lower()


def test_reply_delay_returns_wait_state():
    """Verify deferral request returns wait action with wait_seconds."""
    res = ReplyHandler.handle_reply(
        conversation_id="conv_delay_1",
        merchant_id="m_001",
        customer_id=None,
        from_role="merchant",
        message="I am busy right now, please message me later tomorrow",
        received_at="2026-04-26T12:00:00Z",
        turn_number=2,
    )
    assert res["action"] == "wait"
    assert res.get("wait_seconds", 0) > 0


def test_api_reply_endpoint_integration(client):
    """Verify POST /v1/reply over wire HTTP client."""
    resp = client.post("/v1/reply", json={
        "conversation_id": "conv_wire_1",
        "merchant_id": "m_001",
        "customer_id": None,
        "from_role": "merchant",
        "message": "Ok lets do it. Whats next?",
        "received_at": "2026-04-26T12:00:00Z",
        "turn_number": 2,
    })
    assert resp.status_code == 200
    data = resp.json()
    assert data["action"] == "send"
    assert "draft" in data["body"].lower() or "done" in data["body"].lower()
