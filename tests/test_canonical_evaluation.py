from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.engine.composer import compose
from src.engine.decision import DecisionEngine
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.context_store import context_store

EXPANDED_DIR = Path(__file__).resolve().parent.parent / "expanded"


@pytest.fixture(scope="module")
def loaded_dataset():
    """Load all 355 expanded dataset entities into memory."""
    categories: dict[str, CategoryContext] = {}
    for p in (EXPANDED_DIR / "categories").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            categories[d["slug"]] = CategoryContext.model_validate(d)

    merchants: dict[str, MerchantContext] = {}
    for p in (EXPANDED_DIR / "merchants").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            merchants[d["merchant_id"]] = MerchantContext.model_validate(d)

    customers: dict[str, CustomerContext] = {}
    for p in (EXPANDED_DIR / "customers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            customers[d["customer_id"]] = CustomerContext.model_validate(d)

    triggers: dict[str, TriggerContext] = {}
    for p in (EXPANDED_DIR / "triggers").glob("*.json"):
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
            triggers[d["id"]] = TriggerContext.model_validate(d)

    with open(EXPANDED_DIR / "test_pairs.json", encoding="utf-8") as f:
        pairs = json.load(f)["pairs"]

    return {
        "categories": categories,
        "merchants": merchants,
        "customers": customers,
        "triggers": triggers,
        "pairs": pairs,
    }


def test_all_30_canonical_test_pairs(loaded_dataset):
    """
    Execute composition across all 30 canonical test pairs in expanded/test_pairs.json.
    Asserts zero exceptions, complete grounding, valid CTA vocabulary, and correct send_as scoping.
    """
    cats = loaded_dataset["categories"]
    mers = loaded_dataset["merchants"]
    custs = loaded_dataset["customers"]
    trigs = loaded_dataset["triggers"]
    pairs = loaded_dataset["pairs"]

    assert len(pairs) == 30, "Expected exactly 30 canonical test pairs"

    allowed_ctas = {"binary_yes_no", "open_ended", "binary_confirm_cancel", "multi_choice_slot", "none"}

    for pair in pairs:
        tid = pair["trigger_id"]
        mid = pair["merchant_id"]
        cid = pair["customer_id"]

        trigger = trigs[tid]
        merchant = mers[mid]
        category = cats[merchant.category_slug]
        customer = custs.get(cid) if cid else None

        result = compose(
            category=category,
            merchant=merchant,
            trigger=trigger,
            customer=customer,
        )

        # 1. Structure validation
        assert "body" in result
        assert "cta" in result
        assert "send_as" in result
        assert "suppression_key" in result
        assert "rationale" in result

        # 2. Content quality & grounding checks
        assert len(result["body"]) >= 15, f"Body too short for test {pair['test_id']}"
        assert result["cta"] in allowed_ctas, f"Invalid CTA '{result['cta']}' in test {pair['test_id']}"
        assert "http://" not in result["body"] and "https://" not in result["body"]

        # 3. Scoping checks
        if customer:
            assert result["send_as"] == "merchant_on_behalf"
        else:
            assert result["send_as"] == "vera"

        # 4. Suppression key matching
        assert result["suppression_key"] == trigger.suppression_key


def test_adaptive_context_injection_lifecycle():
    """
    Test Phase 14 adaptive context injection:
    Pushes v1 context, composes, then pushes v2 updated performance and digest,
    verifying that the composer dynamically incorporates the new context.
    """
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        cat_data = json.load(f)
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        mer_data = json.load(f)
    with open(EXPANDED_DIR / "triggers" / "trg_001_research_digest_dentists.json", encoding="utf-8") as f:
        trg_data = json.load(f)

    # Ingest v1
    context_store.upsert("category", "dentists", 1, cat_data)
    context_store.upsert("merchant", mer_data["merchant_id"], 1, mer_data)
    context_store.upsert("trigger", trg_data["id"], 1, trg_data)

    engine = DecisionEngine()
    cand_v1 = engine.select_candidates([trg_data["id"]])[0]
    action_v1 = cand_v1.to_tick_action()
    assert "JIDA Oct 2026" in action_v1["body"]

    # Ingest v2 Category with brand new research digest item
    cat_v2 = dict(cat_data)
    cat_v2["digest"] = [{
        "id": "d_2026W17_jida_fluoride",
        "kind": "research",
        "title": "Fluoride Varnish 3-Month Protocol Revolutionizes Adult Recall",
        "source": "IDA National Journal 2026",
        "summary": "Protocol cut root caries recurrence by 45%.",
        "actionable": "Highlight in adult hygiene recall.",
    }]
    success, _, code = context_store.upsert("category", "dentists", 2, cat_v2)
    assert success is True and code == 200

    # Ingest v2 Trigger referring to the same key with new version
    trg_v2 = dict(trg_data)
    success, _, code = context_store.upsert("trigger", trg_data["id"], 2, trg_v2)
    assert success is True and code == 200

    cand_v2 = engine.select_candidates([trg_data["id"]])[0]
    action_v2 = cand_v2.to_tick_action()
    # Must immediately reflect the updated IDA National Journal citation
    assert "IDA National Journal 2026" in action_v2["body"]
