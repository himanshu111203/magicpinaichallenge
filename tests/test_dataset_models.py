import json
from pathlib import Path
import pytest

from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TestSuite,
    TriggerContext,
)

BASE_DIR = Path(__file__).resolve().parent.parent
EXPANDED_DIR = BASE_DIR / "expanded"


def test_load_all_categories():
    """Verify all 5 category files load and validate without error."""
    category_files = list((EXPANDED_DIR / "categories").glob("*.json"))
    assert len(category_files) == 5, f"Expected 5 category files, found {len(category_files)}"

    categories = {}
    for p in category_files:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        cat = CategoryContext.model_validate(data)
        assert cat.slug == data["slug"]
        assert len(cat.offer_catalog) == 8
        assert len(cat.digest) == 5
        assert cat.peer_stats.avg_rating > 0
        categories[cat.slug] = cat

    # Verify category-specific peer_stats variations
    assert categories["dentists"].peer_stats.retention_6mo_pct is not None
    assert categories["salons"].peer_stats.retention_3mo_pct is not None
    assert categories["restaurants"].peer_stats.retention_30d_pct is not None
    assert categories["gyms"].peer_stats.monthly_churn_pct is not None
    assert categories["pharmacies"].peer_stats.delivery_share_pct is not None


def test_load_all_merchants():
    """Verify all 50 merchant files load and validate without error."""
    merchant_files = list((EXPANDED_DIR / "merchants").glob("*.json"))
    assert len(merchant_files) == 50, f"Expected 50 merchant files, found {len(merchant_files)}"

    statuses = set()
    for p in merchant_files:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        merchant = MerchantContext.model_validate(data)
        assert merchant.merchant_id == data["merchant_id"]
        assert merchant.identity.name
        assert merchant.performance.window_days == 30
        statuses.add(merchant.subscription.status)

    assert statuses == {"active", "trial", "expired"}, f"Unexpected subscription statuses: {statuses}"


def test_load_all_customers():
    """Verify all 200 customer files load and validate without error."""
    customer_files = list((EXPANDED_DIR / "customers").glob("*.json"))
    assert len(customer_files) == 200, f"Expected 200 customer files, found {len(customer_files)}"

    for p in customer_files:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        customer = CustomerContext.model_validate(data)
        assert customer.customer_id == data["customer_id"]
        assert customer.merchant_id == data["merchant_id"]


def test_anonymous_customer_edge_case():
    """
    Assert the model properly handles the walk-in customer with no profile or consent:
    c_015_anonymous_for_m010 has phone_redacted: null and opted_in_at: null.
    """
    c15_file = EXPANDED_DIR / "customers" / "c_015_anonymous_for_m010.json"
    assert c15_file.exists(), "c_015_anonymous_for_m010.json must exist in expanded/customers"

    with open(c15_file, encoding="utf-8") as f:
        data = json.load(f)

    customer = CustomerContext.model_validate(data)
    assert customer.customer_id == "c_015_anonymous_for_m010"
    assert customer.identity.phone_redacted is None
    assert customer.identity.name == "(walk-in, no profile)"
    assert customer.consent.opted_in_at is None
    assert customer.consent.scope == []
    assert customer.has_valid_consent is False
    assert customer.is_anonymous_or_walkin is True


def test_load_all_triggers():
    """Verify all 100 trigger files load and validate without error."""
    trigger_files = list((EXPANDED_DIR / "triggers").glob("*.json"))
    assert len(trigger_files) == 100, f"Expected 100 trigger files, found {len(trigger_files)}"

    placeholder_count = 0
    seed_count = 0
    for p in trigger_files:
        with open(p, encoding="utf-8") as f:
            data = json.load(f)
        trigger = TriggerContext.model_validate(data)
        assert trigger.id == data["id"]
        assert 1 <= trigger.urgency <= 5
        assert trigger.suppression_key

        if trigger.is_placeholder_payload:
            placeholder_count += 1
        else:
            seed_count += 1

    assert placeholder_count == 75, f"Expected 75 placeholder triggers, found {placeholder_count}"
    assert seed_count == 25, f"Expected 25 seed triggers, found {seed_count}"


def test_placeholder_payload_trigger():
    """Verify placeholder-payload trigger handling and helper properties."""
    # Find a placeholder trigger
    trigger_files = list((EXPANDED_DIR / "triggers").glob("*.json"))
    placeholder_file = None
    for p in trigger_files:
        with open(p, encoding="utf-8") as f:
            d = json.load(f)
        if d.get("payload", {}).get("placeholder") is True:
            placeholder_file = p
            break

    assert placeholder_file is not None, "A placeholder trigger must exist in expanded/triggers"
    with open(placeholder_file, encoding="utf-8") as f:
        data = json.load(f)

    trigger = TriggerContext.model_validate(data)
    assert trigger.is_placeholder_payload is True
    assert trigger.payload.is_placeholder is True
    assert trigger.payload.metric_or_topic == trigger.kind
    assert trigger.payload.get("metric_or_topic") == trigger.kind
    assert trigger.payload.get("nonexistent_field", "default_val") == "default_val"


def test_seed_payload_trigger():
    """Verify seed trigger with rich payload preserves extra fields."""
    seed_file = EXPANDED_DIR / "triggers" / "trg_003_recall_due_priya.json"
    assert seed_file.exists(), "trg_003_recall_due_priya.json must exist in expanded/triggers"

    with open(seed_file, encoding="utf-8") as f:
        data = json.load(f)

    trigger = TriggerContext.model_validate(data)
    assert trigger.is_placeholder_payload is False
    assert trigger.payload.is_placeholder is False
    assert trigger.payload.get("service_due") == "6_month_cleaning"
    assert trigger.payload.get("due_date") == "2026-11-12"


def test_canonical_test_pairs():
    """Verify expanded/test_pairs.json loads and references valid entities."""
    test_pairs_file = EXPANDED_DIR / "test_pairs.json"
    assert test_pairs_file.exists(), "test_pairs.json must exist in expanded"

    with open(test_pairs_file, encoding="utf-8") as f:
        data = json.load(f)

    suite = TestSuite.model_validate(data)
    assert len(suite.pairs) == 30, f"Expected 30 canonical pairs, found {len(suite.pairs)}"

    # Check test ID format
    for idx, pair in enumerate(suite.pairs, start=1):
        assert pair.test_id == f"T{idx:02d}"
        assert pair.trigger_id
        assert pair.merchant_id
