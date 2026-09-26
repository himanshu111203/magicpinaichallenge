from __future__ import annotations

import json
from pathlib import Path
import pytest
from fastapi.testclient import TestClient

from src.engine.decision import DecisionEngine, RankedCandidate
from src.engine.semantic_family import TriggerFamily, classify_trigger_family
from src.engine.signal_selector import CandidateSignalBundle, SignalSelector
from src.engine.suppression import suppression_engine
from src.main import app
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.context_store import context_store

EXPANDED_DIR = Path(__file__).resolve().parent.parent / "expanded"


@pytest.fixture(autouse=True)
def reset_stores():
    """Reset context store and suppression engine before each test."""
    context_store.clear()
    suppression_engine._used_suppression_keys.clear()
    suppression_engine._tick_merchants.clear()
    suppression_engine._tick_action_count = 0
    yield
    context_store.clear()
    suppression_engine._used_suppression_keys.clear()
    suppression_engine._tick_merchants.clear()
    suppression_engine._tick_action_count = 0


@pytest.fixture
def client():
    return TestClient(app)


# =============================================================================
# 1. Semantic Family Classification Tests
# =============================================================================

def test_classify_trigger_family_seed_kinds():
    """Test classification of all known canonical seed trigger kinds."""
    assert classify_trigger_family("recall_due") == TriggerFamily.RECALL_REMINDER
    assert classify_trigger_family("chronic_refill_due") == TriggerFamily.RECALL_REMINDER
    assert classify_trigger_family("perf_dip") == TriggerFamily.PERFORMANCE_MOVEMENT
    assert classify_trigger_family("perf_spike") == TriggerFamily.PERFORMANCE_MOVEMENT
    assert classify_trigger_family("dormant_with_vera") == TriggerFamily.DORMANCY_LAPSE
    assert classify_trigger_family("winback_eligible") == TriggerFamily.DORMANCY_LAPSE
    assert classify_trigger_family("renewal_due") == TriggerFamily.DORMANCY_LAPSE
    assert classify_trigger_family("research_digest") == TriggerFamily.RESEARCH_COMPLIANCE_TREND
    assert classify_trigger_family("regulation_change") == TriggerFamily.RESEARCH_COMPLIANCE_TREND
    assert classify_trigger_family("milestone_reached") == TriggerFamily.MILESTONE
    assert classify_trigger_family("review_theme_emerged") == TriggerFamily.MILESTONE
    assert classify_trigger_family("active_planning_intent") == TriggerFamily.PLANNING_INTENT
    assert classify_trigger_family("supply_alert") == TriggerFamily.SUPPLY_ALERT
    assert classify_trigger_family("festival_upcoming") == TriggerFamily.SEASONAL_EVENT
    assert classify_trigger_family("ipl_match_today") == TriggerFamily.SEASONAL_EVENT


def test_classify_trigger_family_generator_and_fuzzy_kinds():
    """Test classification of generated and fuzzy/unseen kinds."""
    assert classify_trigger_family("customer_lapsed_soft") == TriggerFamily.DORMANCY_LAPSE
    assert classify_trigger_family("customer_lapsed_hard") == TriggerFamily.DORMANCY_LAPSE
    assert classify_trigger_family("appointment_tomorrow") == TriggerFamily.RECALL_REMINDER
    assert classify_trigger_family("corporate_thali_planning") == TriggerFamily.PLANNING_INTENT
    assert classify_trigger_family("kids_yoga_program_drafting") == TriggerFamily.PLANNING_INTENT
    assert classify_trigger_family("summer_demand_shift") == TriggerFamily.SEASONAL_EVENT
    # Fuzzy substrings
    assert classify_trigger_family("quarterly_recall_checkup") == TriggerFamily.RECALL_REMINDER
    assert classify_trigger_family("new_regulation_dci_dose") == TriggerFamily.RESEARCH_COMPLIANCE_TREND
    assert classify_trigger_family("unseen_strange_kind") == TriggerFamily.GENERAL_NUDGE


# =============================================================================
# 2. Grounded Signal Selector Tests
# =============================================================================

def test_signal_selector_seed_rich_payload():
    """Verify signal extraction from a rich seed trigger preserves exact citations and numbers."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        category = CategoryContext.model_validate(json.load(f))
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        merchant = MerchantContext.model_validate(json.load(f))
    with open(EXPANDED_DIR / "triggers" / "trg_001_research_digest_dentists.json", encoding="utf-8") as f:
        trigger = TriggerContext.model_validate(json.load(f))

    signals = SignalSelector.extract_signals(trigger, merchant, category)

    assert signals.semantic_family == TriggerFamily.RESEARCH_COMPLIANCE_TREND
    assert signals.is_placeholder_payload is False
    assert signals.merchant_name == "Dr. Meera's Dental Clinic"
    assert signals.owner_first_name == "Meera"
    assert signals.locality == "Lajpat Nagar"
    assert signals.digest_item_title is not None
    assert "fluoride" in signals.digest_item_title.lower()
    assert signals.digest_item_source == "JIDA Oct 2026, p.14"

    # Verify every grounded fact has an explicit provenance source
    for fact in signals.grounded_facts:
        assert fact.source is not None
        assert fact.value is not None


def test_signal_selector_placeholder_graceful_degradation():
    """Verify placeholder payload triggers fall back to genuine merchant signals without fabricating."""
    # Find any placeholder trigger in expanded dataset
    placeholder_file = None
    for p in (EXPANDED_DIR / "triggers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("payload", {}).get("placeholder") is True:
            placeholder_file = p
            trigger_data = d
            break

    assert placeholder_file is not None
    trigger = TriggerContext.model_validate(trigger_data)

    # Find the corresponding merchant file
    merchant_file = next((EXPANDED_DIR / "merchants").glob(f"{trigger.merchant_id}*.json"))
    with open(merchant_file, encoding="utf-8") as f:
        merchant = MerchantContext.model_validate(json.load(f))

    with open(EXPANDED_DIR / "categories" / f"{merchant.category_slug}.json", encoding="utf-8") as f:
        category = CategoryContext.model_validate(json.load(f))

    signals = SignalSelector.extract_signals(trigger, merchant, category)
    assert signals.is_placeholder_payload is True
    assert signals.merchant_name == merchant.identity.name
    assert signals.locality == merchant.identity.locality

    # Verify all extracted facts are genuinely grounded in source context
    assert len(signals.grounded_facts) >= 4  # Name, owner, locality, city + any performance/offers
    for fact in signals.grounded_facts:
        assert fact.source is not None
        assert fact.value is not None



# =============================================================================
# 3. Decision Engine & Priority Ranking Tests
# =============================================================================

def test_decision_engine_ranking_and_renewal_priority():
    """Verify candidates are scored deterministically and renewal due is prioritized."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        category = json.load(f)
    context_store.upsert("category", "dentists", 1, category)

    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        m1_data = json.load(f)
    context_store.upsert("merchant", m1_data["merchant_id"], 1, m1_data)

    with open(EXPANDED_DIR / "merchants" / "m_002_bharat_dentist_mumbai.json", encoding="utf-8") as f:
        m2_data = json.load(f)
    # Set m2 subscription to renewal due in 3 days
    m2_data["subscription"]["status"] = "active"
    m2_data["subscription"]["days_remaining"] = 3
    context_store.upsert("merchant", m2_data["merchant_id"], 1, m2_data)

    # Trigger 1: Routine curiosity trigger (Urgency 1) for m1
    trg1_data = {
        "id": "trg_test_curiosity_m1",
        "scope": "merchant",
        "kind": "curious_ask_due",
        "source": "internal",
        "merchant_id": m1_data["merchant_id"],
        "customer_id": None,
        "payload": {"placeholder": False, "topic": "teeth whitening queries"},
        "urgency": 2,
        "suppression_key": "curious:m1:w1",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    context_store.upsert("trigger", trg1_data["id"], 1, trg1_data)

    # Trigger 2: Renewal due (Urgency 4) for m2
    trg2_data = {
        "id": "trg_test_renewal_m2",
        "scope": "merchant",
        "kind": "renewal_due",
        "source": "internal",
        "merchant_id": m2_data["merchant_id"],
        "customer_id": None,
        "payload": {"days_remaining": 3, "plan": "Pro"},
        "urgency": 4,
        "suppression_key": "renewal:m2:w1",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    context_store.upsert("trigger", trg2_data["id"], 1, trg2_data)

    engine = DecisionEngine()
    candidates = engine.select_candidates(["trg_test_curiosity_m1", "trg_test_renewal_m2"])

    assert len(candidates) == 2
    # Renewal due must rank first due to higher urgency + renewal boost (+35)
    assert candidates[0].trigger.id == "trg_test_renewal_m2"
    assert candidates[0].priority_score > candidates[1].priority_score
    assert any("renewal_due" in r for r in candidates[0].score_reasons)


def test_decision_engine_per_merchant_deduplication():
    """Verify only 1 action per merchant is selected even if multiple triggers exist (FAQ §14)."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        context_store.upsert("category", "dentists", 1, json.load(f))
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        m1 = json.load(f)
        context_store.upsert("merchant", m1["merchant_id"], 1, m1)

    # Low urgency trigger for m1
    trg_low = {
        "id": "trg_m1_low",
        "scope": "merchant",
        "kind": "milestone_reached",
        "source": "internal",
        "merchant_id": m1["merchant_id"],
        "customer_id": None,
        "payload": {"milestone": "50 reviews"},
        "urgency": 2,
        "suppression_key": "milestone:m1:50",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    # High urgency trigger for same m1
    trg_high = {
        "id": "trg_m1_high",
        "scope": "merchant",
        "kind": "perf_dip",
        "source": "internal",
        "merchant_id": m1["merchant_id"],
        "customer_id": None,
        "payload": {"metric": "calls", "delta_pct": -40},
        "urgency": 4,
        "suppression_key": "perf_dip:m1:calls",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    context_store.upsert("trigger", trg_low["id"], 1, trg_low)
    context_store.upsert("trigger", trg_high["id"], 1, trg_high)

    engine = DecisionEngine()
    candidates = engine.select_candidates([trg_low["id"], trg_high["id"]])

    # Exactly 1 candidate chosen for m1, and it must be the higher urgency one
    assert len(candidates) == 1
    assert candidates[0].trigger.id == "trg_m1_high"
    assert candidates[0].merchant.merchant_id == m1["merchant_id"]


def test_decision_engine_filters_unconsented_customer():
    """Verify triggers targeting anonymous unconsented walk-in are rejected."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        context_store.upsert("category", "dentists", 1, json.load(f))
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        m1 = json.load(f)
        context_store.upsert("merchant", m1["merchant_id"], 1, m1)
    with open(EXPANDED_DIR / "customers" / "c_015_anonymous_for_m010.json", encoding="utf-8") as f:
        c15 = json.load(f)
        context_store.upsert("customer", c15["customer_id"], 1, c15)

    trg_unconsented = {
        "id": "trg_walkin_recall",
        "scope": "customer",
        "kind": "recall_due",
        "source": "internal",
        "merchant_id": m1["merchant_id"],
        "customer_id": c15["customer_id"],
        "payload": {"placeholder": False, "recommended_service": "cleaning"},
        "urgency": 4,
        "suppression_key": f"recall:{c15['customer_id']}:1",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    context_store.upsert("trigger", trg_unconsented["id"], 1, trg_unconsented)

    engine = DecisionEngine()
    candidates = engine.select_candidates([trg_unconsented["id"]])
    assert len(candidates) == 0  # Pre-flight suppression gate drops unconsented customer


# =============================================================================
# 4. End-to-End POST /v1/tick Integration Tests
# =============================================================================

def test_api_tick_end_to_end(client):
    """Test full /v1/tick lifecycle from context ingestion to ranked action dispatch."""
    # 1. Ingest Category
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        resp = client.post("/v1/context", json={
            "scope": "category",
            "context_id": "dentists",
            "version": 1,
            "payload": json.load(f),
        })
        assert resp.status_code == 200

    # 2. Ingest Merchant
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        m_data = json.load(f)
        resp = client.post("/v1/context", json={
            "scope": "merchant",
            "context_id": m_data["merchant_id"],
            "version": 1,
            "payload": m_data,
        })
        assert resp.status_code == 200

    # 3. Ingest Trigger (rich seed)
    with open(EXPANDED_DIR / "triggers" / "trg_001_research_digest_dentists.json", encoding="utf-8") as f:
        t_data = json.load(f)
        resp = client.post("/v1/context", json={
            "scope": "trigger",
            "context_id": t_data["id"],
            "version": 1,
            "payload": t_data,
        })
        assert resp.status_code == 200

    # 4. Call POST /v1/tick
    tick_resp = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [t_data["id"]],
    })
    assert tick_resp.status_code == 200
    data = tick_resp.json()
    assert "actions" in data
    actions = data["actions"]
    assert len(actions) == 1

    action = actions[0]
    assert action["merchant_id"] == "m_001_drmeera_dentist_delhi"
    assert action["trigger_id"] == "trg_001_research_digest_dentists"
    assert action["send_as"] == "vera"
    assert action["cta"] in ("binary_yes_no", "open_ended", "multi_choice_slot")
    assert action["suppression_key"] == t_data["suppression_key"]
    assert "JIDA Oct 2026" in action["body"]
    assert "Meera" in action["body"]
    assert action["rationale"] is not None


    # 5. Call POST /v1/tick again in same tick: action must be suppressed due to suppression key & merchant limit
    tick_resp_2 = client.post("/v1/tick", json={
        "now": "2026-04-26T10:00:00Z",
        "available_triggers": [t_data["id"]],
    })
    assert tick_resp_2.status_code == 200
    assert tick_resp_2.json()["actions"] == []


def test_decision_engine_global_tick_action_cap():
    """Verify that when >20 merchants have eligible candidates, only the top 20 are returned."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        category = json.load(f)
    context_store.upsert("category", "dentists", 1, category)

    trigger_ids = []
    # Create 25 merchants with 1 trigger each
    for i in range(1, 26):
        mid = f"m_test_{i:03d}"
        m_data = {
            "merchant_id": mid,
            "category_slug": "dentists",
            "identity": {
                "name": f"Clinic {i}",
                "city": "Delhi",
                "locality": "South Ext",
                "place_id": f"pid_{i}",
                "verified": True,
                "languages": ["English"],
                "owner_first_name": f"Doctor{i}",
                "established_year": 2020,
            },
            "subscription": {"status": "active", "plan": "Pro", "days_remaining": 60},
            "performance": {"window_days": 30, "views": 1000, "calls": 50, "directions": 20, "ctr": 0.04, "leads": 10},
            "offers": [{"id": f"off_{i}", "title": "Free Checkup", "status": "active"}],
            "customer_aggregate": {"total_unique_ytd": 200},
            "signals": [],
            "review_themes": [],
        }
        context_store.upsert("merchant", mid, 1, m_data)

        tid = f"trg_test_{i:03d}"
        t_data = {
            "id": tid,
            "scope": "merchant",
            "kind": "curious_ask_due",
            "source": "internal",
            "merchant_id": mid,
            "customer_id": None,
            "payload": {"placeholder": False, "topic": f"topic {i}"},
            # Urgency varies from 1 to 5 to check score sorting
            "urgency": (i % 5) + 1,
            "suppression_key": f"curious:{mid}:w1",
            "expires_at": "2026-05-01T00:00:00Z",
        }
        context_store.upsert("trigger", tid, 1, t_data)
        trigger_ids.append(tid)

    engine = DecisionEngine()
    selected = engine.select_candidates(trigger_ids)

    # Exactly MAX_ACTIONS_PER_TICK (20) selected
    assert len(selected) == 20
    # Must be sorted descending by priority score
    scores = [c.priority_score for c in selected]
    assert scores == sorted(scores, reverse=True)


def test_decision_engine_restraint_filter():
    """Verify that thin placeholder triggers with low urgency are dropped under the restraint rule."""
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        context_store.upsert("category", "dentists", 1, json.load(f))

    mid = "m_thin_merchant"
    m_data = {
        "merchant_id": mid,
        "category_slug": "dentists",
        "identity": {
            "name": "Thin Clinic",
            "city": "Delhi",
            "locality": "Rohini",
            "place_id": "pid_thin",
            "verified": True,
            "languages": ["English"],
            "owner_first_name": "Doctor",
            "established_year": 2020,
        },
        "subscription": {"status": "active", "plan": "Basic", "days_remaining": 60},
        "performance": {"window_days": 30, "views": 100, "calls": 5, "directions": 2, "ctr": 0.01, "leads": 0},
        "offers": [],  # No active offers
        "customer_aggregate": {"total_unique_ytd": 20},
        "signals": [],  # No signals
        "review_themes": [],
    }
    context_store.upsert("merchant", mid, 1, m_data)

    # Low urgency placeholder trigger with zero actionable context
    tid = "trg_thin_placeholder"
    t_data = {
        "id": tid,
        "scope": "merchant",
        "kind": "curious_ask_due",
        "source": "internal",
        "merchant_id": mid,
        "customer_id": None,
        "payload": {"placeholder": True, "metric_or_topic": "curious_ask_due"},
        "urgency": 1,
        "suppression_key": "curious:thin:w1",
        "expires_at": "2026-05-01T00:00:00Z",
    }
    context_store.upsert("trigger", tid, 1, t_data)

    engine = DecisionEngine()
    selected = engine.select_candidates([tid])

    # Dropped by restraint threshold (urgency 1 * 15 - 10 penalty = 5 < 25 MIN_SCORE_THRESHOLD)
    assert len(selected) == 0

