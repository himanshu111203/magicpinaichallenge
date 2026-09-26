import json
from pathlib import Path
import pytest

from src.engine import (
    MAX_ACTIONS_PER_TICK,
    SuppressionEngine,
    SuppressionReason,
)
from src.models import (
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.conversation_store import conversation_store

BASE_DIR = Path(__file__).resolve().parent.parent
EXPANDED_DIR = BASE_DIR / "expanded"


@pytest.fixture
def engine():
    e = SuppressionEngine()
    conversation_store.clear()
    return e


@pytest.fixture
def sample_merchant():
    m_path = EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json"
    with open(m_path, encoding="utf-8") as f:
        return MerchantContext.model_validate(json.load(f))


@pytest.fixture
def sample_trigger():
    t_path = next((EXPANDED_DIR / "triggers").glob("*trg_001*"))
    with open(t_path, encoding="utf-8") as f:
        return TriggerContext.model_validate(json.load(f))


def test_hard_suppression_anonymous_walkin(engine, sample_merchant):
    """
    CRITICAL EDGE CASE:
    c_015_anonymous_for_m010 has no profile, phone_redacted=null, and opted_in_at=null.
    Engine must strictly suppress any customer-facing trigger with zero exceptions.
    """
    c_path = EXPANDED_DIR / "customers" / "c_015_anonymous_for_m010.json"
    with open(c_path, encoding="utf-8") as f:
        anonymous_cust = CustomerContext.model_validate(json.load(f))

    # Create a trigger targeting this anonymous customer
    trigger_data = {
        "id": "trg_test_anon",
        "scope": "customer",
        "kind": "recall_due",
        "source": "internal",
        "merchant_id": sample_merchant.merchant_id,
        "customer_id": anonymous_cust.customer_id,
        "payload": {"placeholder": False, "service_due": "checkup"},
        "urgency": 3,
        "suppression_key": f"recall:{anonymous_cust.customer_id}:test",
        "expires_at": "2026-12-31T23:59:59",
    }
    trigger = TriggerContext.model_validate(trigger_data)

    decision = engine.check_trigger_suppression(
        trigger=trigger,
        merchant=sample_merchant,
        customer=anonymous_cust,
    )

    assert decision.suppressed is True
    assert decision.reason in (
        SuppressionReason.ANONYMOUS_WALKIN,
        SuppressionReason.NO_CONSENT,
        SuppressionReason.NO_PHONE,
    )


def test_customer_with_valid_consent_allowed(engine, sample_merchant):
    """Customers with phone and active consent should pass consent check."""
    c_path = EXPANDED_DIR / "customers" / "c_001_priya_for_m001.json"
    with open(c_path, encoding="utf-8") as f:
        valid_cust = CustomerContext.model_validate(json.load(f))

    assert valid_cust.has_valid_consent is True

    trigger_data = {
        "id": "trg_test_priya",
        "scope": "customer",
        "kind": "recall_due",
        "source": "internal",
        "merchant_id": sample_merchant.merchant_id,
        "customer_id": valid_cust.customer_id,
        "payload": {"placeholder": False},
        "urgency": 3,
        "suppression_key": f"recall:{valid_cust.customer_id}:6mo",
        "expires_at": "2026-12-31T23:59:59",
    }
    trigger = TriggerContext.model_validate(trigger_data)

    decision = engine.check_trigger_suppression(
        trigger=trigger,
        merchant=sample_merchant,
        customer=valid_cust,
    )
    assert decision.suppressed is False


def test_customer_scoped_trigger_missing_customer_suppressed(engine, sample_merchant):
    """Customer-scoped trigger missing CustomerContext must be suppressed."""
    trigger_data = {
        "id": "trg_test_nocust",
        "scope": "customer",
        "kind": "recall_due",
        "source": "internal",
        "merchant_id": sample_merchant.merchant_id,
        "customer_id": "c_missing",
        "payload": {},
        "urgency": 3,
        "suppression_key": "recall:c_missing:6mo",
        "expires_at": "2026-12-31T23:59:59",
    }
    trigger = TriggerContext.model_validate(trigger_data)

    decision = engine.check_trigger_suppression(
        trigger=trigger,
        merchant=sample_merchant,
        customer=None,
    )
    assert decision.suppressed is True
    assert decision.reason == SuppressionReason.NO_CONSENT


def test_suppression_key_deduplication(engine, sample_merchant, sample_trigger):
    """Once a suppression_key is acted on, subsequent attempts on that key are blocked."""
    # 1. First evaluation: allowed
    d1 = engine.check_trigger_suppression(sample_trigger, sample_merchant)
    assert d1.suppressed is False

    # 2. Record action
    engine.record_action(
        trigger=sample_trigger,
        conversation_id="conv_test_1",
        body="Dr. Meera, new study on oral systemic health.",
        now_iso="2026-04-26T10:00:00Z",
    )
    assert engine.is_key_suppressed(sample_trigger.suppression_key) is True

    # 3. Second evaluation: blocked by KEY_ALREADY_SUPPRESSED
    engine.start_tick()  # New tick, so merchant limit resets
    d2 = engine.check_trigger_suppression(sample_trigger, sample_merchant)
    assert d2.suppressed is True
    assert d2.reason == SuppressionReason.KEY_ALREADY_SUPPRESSED


def test_per_merchant_tick_rate_limit(engine, sample_merchant):
    """Max 1 action per merchant per tick (FAQ §14)."""
    t1_data = {
        "id": "trg_m1_1",
        "scope": "merchant",
        "kind": "perf_dip",
        "source": "internal",
        "merchant_id": sample_merchant.merchant_id,
        "payload": {},
        "urgency": 4,
        "suppression_key": "perf_dip:m1:calls:W17",
        "expires_at": "2026-12-31T23:59:59",
    }
    t2_data = {
        "id": "trg_m1_2",
        "scope": "merchant",
        "kind": "curious_ask_due",
        "source": "internal",
        "merchant_id": sample_merchant.merchant_id,
        "payload": {},
        "urgency": 1,
        "suppression_key": "curious:m1:W17",
        "expires_at": "2026-12-31T23:59:59",
    }
    t1 = TriggerContext.model_validate(t1_data)
    t2 = TriggerContext.model_validate(t2_data)

    engine.start_tick()

    # t1 allowed and recorded
    assert engine.check_trigger_suppression(t1, sample_merchant).suppressed is False
    engine.record_action(t1, "conv_1", "Your calls dipped.")

    # t2 blocked because merchant already messaged in this tick
    d2 = engine.check_trigger_suppression(t2, sample_merchant)
    assert d2.suppressed is True
    assert d2.reason == SuppressionReason.MERCHANT_TICK_LIMIT

    # Advance tick: merchant can now be messaged with t2 (which has a different suppression key)
    engine.start_tick()
    d3 = engine.check_trigger_suppression(t2, sample_merchant)
    assert d3.suppressed is False


def test_global_tick_action_cap(engine, sample_merchant):
    """Global tick limit of 20 actions per tick."""
    engine.start_tick()

    # Simulate 20 actions for 20 distinct merchants
    for i in range(MAX_ACTIONS_PER_TICK):
        t_data = {
            "id": f"trg_{i}",
            "scope": "merchant",
            "kind": "research_digest",
            "source": "external",
            "merchant_id": f"m_{i:03d}",
            "payload": {},
            "urgency": 2,
            "suppression_key": f"key_{i}",
            "expires_at": "2026-12-31T23:59:59",
        }
        t = TriggerContext.model_validate(t_data)
        engine.record_action(t, f"conv_{i}", f"Message {i}")

    # 21st action should be blocked by TICK_ACTION_CAP
    t21_data = {
        "id": "trg_21",
        "scope": "merchant",
        "kind": "research_digest",
        "source": "external",
        "merchant_id": "m_999",
        "payload": {},
        "urgency": 2,
        "suppression_key": "key_21",
        "expires_at": "2026-12-31T23:59:59",
    }
    t21 = TriggerContext.model_validate(t21_data)
    d = engine.check_trigger_suppression(t21)
    assert d.suppressed is True
    assert d.reason == SuppressionReason.TICK_ACTION_CAP


def test_expired_trigger_suppressed(engine, sample_merchant):
    """Triggers past their expires_at date are suppressed."""
    trigger_data = {
        "id": "trg_expired",
        "scope": "merchant",
        "kind": "festival_upcoming",
        "source": "external",
        "merchant_id": sample_merchant.merchant_id,
        "payload": {},
        "urgency": 1,
        "suppression_key": "fest:diwali:past",
        "expires_at": "2026-04-20T10:00:00Z",
    }
    trigger = TriggerContext.model_validate(trigger_data)

    decision = engine.check_trigger_suppression(
        trigger=trigger,
        merchant=sample_merchant,
        now_iso="2026-04-26T10:00:00Z",
    )
    assert decision.suppressed is True
    assert decision.reason == SuppressionReason.EXPIRED_TRIGGER


def test_expired_merchant_subscription_handling(engine):
    """Expired merchants reject regular nudges but allow winback / renewal triggers."""
    m_path = EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json"
    with open(m_path, encoding="utf-8") as f:
        data = json.load(f)
    data["subscription"]["status"] = "expired"
    expired_merchant = MerchantContext.model_validate(data)

    # Regular trigger -> suppressed
    reg_trigger = TriggerContext.model_validate({
        "id": "trg_reg", "scope": "merchant", "kind": "curious_ask_due", "source": "internal",
        "merchant_id": expired_merchant.merchant_id, "payload": {}, "urgency": 1,
        "suppression_key": "curious:exp", "expires_at": "2026-12-31T23:59:59"
    })
    d1 = engine.check_trigger_suppression(reg_trigger, expired_merchant)
    assert d1.suppressed is True
    assert d1.reason == SuppressionReason.MERCHANT_INACTIVE_EXPIRED

    # Winback / Renewal trigger -> allowed
    winback_trigger = TriggerContext.model_validate({
        "id": "trg_win", "scope": "merchant", "kind": "winback_eligible", "source": "internal",
        "merchant_id": expired_merchant.merchant_id, "payload": {}, "urgency": 4,
        "suppression_key": "winback:exp", "expires_at": "2026-12-31T23:59:59"
    })
    d2 = engine.check_trigger_suppression(winback_trigger, expired_merchant)
    assert d2.suppressed is False


def test_anti_repetition_verbatim_body_suppressed(engine, sample_merchant, sample_trigger):
    """Verbatim body repetition within the same conversation is caught and suppressed."""
    conv_id = "conv_rep_test"
    body_text = "Good morning Doctor. Here is this week's research update."

    # Record first action
    engine.record_action(sample_trigger, conv_id, body_text)

    # Proposed duplicate body
    rep_decision = engine.check_body_repetition(conv_id, body_text)
    assert rep_decision.suppressed is True
    assert rep_decision.reason == SuppressionReason.VERBATIM_BODY_REPEAT

    # Non-duplicate body allowed
    diff_decision = engine.check_body_repetition(conv_id, "Different message content.")
    assert diff_decision.suppressed is False
