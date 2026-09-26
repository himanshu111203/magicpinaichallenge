from __future__ import annotations

import json
from pathlib import Path
import pytest

from src.engine.composer import compose
from src.engine.voice_validator import VoiceValidator
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)

EXPANDED_DIR = Path(__file__).resolve().parent.parent / "expanded"


@pytest.fixture
def dentists_category():
    with open(EXPANDED_DIR / "categories" / "dentists.json", encoding="utf-8") as f:
        return CategoryContext.model_validate(json.load(f))


@pytest.fixture
def meera_merchant():
    with open(EXPANDED_DIR / "merchants" / "m_001_drmeera_dentist_delhi.json", encoding="utf-8") as f:
        return MerchantContext.model_validate(json.load(f))


@pytest.fixture
def fluoride_trigger():
    with open(EXPANDED_DIR / "triggers" / "trg_001_research_digest_dentists.json", encoding="utf-8") as f:
        return TriggerContext.model_validate(json.load(f))


@pytest.fixture
def priya_customer():
    with open(EXPANDED_DIR / "customers" / "c_001_priya_for_m001.json", encoding="utf-8") as f:
        return CustomerContext.model_validate(json.load(f))


def test_compose_pure_function_merchant_facing(dentists_category, meera_merchant, fluoride_trigger):
    """Test pure compose() output structure and grounding for merchant-facing digest trigger."""
    result = compose(
        category=dentists_category,
        merchant=meera_merchant,
        trigger=fluoride_trigger,
    )

    assert isinstance(result, dict)
    assert set(result.keys()) == {"body", "cta", "send_as", "suppression_key", "rationale"}
    assert result["send_as"] == "vera"
    assert result["suppression_key"] == fluoride_trigger.suppression_key
    assert result["cta"] in ("binary_yes_no", "open_ended", "multi_choice_slot")
    assert "JIDA Oct 2026" in result["body"]
    assert "Meera" in result["body"]
    assert len(result["rationale"]) > 10


def test_compose_pure_function_customer_facing(dentists_category, meera_merchant, fluoride_trigger, priya_customer):
    """Test customer-facing compose output marks send_as='merchant_on_behalf'."""
    result = compose(
        category=dentists_category,
        merchant=meera_merchant,
        trigger=fluoride_trigger,
        customer=priya_customer,
    )

    assert result["send_as"] == "merchant_on_behalf"
    assert "Priya" in result["body"]
    assert "Dr. Meera" in result["body"]


def test_compose_accepts_raw_dicts(dentists_category, meera_merchant, fluoride_trigger):
    """Verify compose() seamlessly accepts raw python dicts (per brief §5)."""
    result = compose(
        category=dentists_category.model_dump(),
        merchant=meera_merchant.model_dump(by_alias=True),
        trigger=fluoride_trigger.model_dump(),
    )
    assert isinstance(result, dict)
    assert result["send_as"] == "vera"
    assert "body" in result


def test_voice_validator_strips_urls():
    """Verify URLs are stripped from body text to avoid the hard -3 penalty."""
    text_with_url = "Check out our new clinic website at https://example.com/clinic and book today!"
    cleaned = VoiceValidator.sanitize_body(text_with_url)
    assert "https://" not in cleaned
    assert "example.com" not in cleaned


def test_voice_validator_neutralizes_taboos(dentists_category):
    """Verify forbidden medical taboos ('guaranteed', 'cure') are neutralized."""
    text = "We offer a guaranteed cure for tooth decay with 100% relief!"
    cleaned = VoiceValidator.sanitize_body(text, dentists_category)
    assert "guaranteed" not in cleaned.lower()


def test_all_five_verticals_compose_cleanly():
    """Verify strategies for all 5 verticals produce valid, grounded copy."""
    slugs = ["dentists", "salons", "restaurants", "gyms", "pharmacies"]

    for slug in slugs:
        with open(EXPANDED_DIR / "categories" / f"{slug}.json", encoding="utf-8") as f:
            cat = json.load(f)

        mer = None
        for p in (EXPANDED_DIR / "merchants").glob("*.json"):
            with open(p, encoding="utf-8") as mf:
                m_json = json.load(mf)
            if m_json.get("category_slug") == slug:
                mer = m_json
                break

        assert mer is not None, f"Merchant for category '{slug}' must exist"



        dummy_trigger = {
            "id": f"trg_test_{slug}",
            "scope": "merchant",
            "kind": "curious_ask_due",
            "source": "internal",
            "merchant_id": mer["merchant_id"],
            "customer_id": None,
            "payload": {"placeholder": False, "topic": "visibility"},
            "urgency": 2,
            "suppression_key": f"test:{slug}",
            "expires_at": "2026-05-01T00:00:00Z",
        }

        res = compose(cat, mer, dummy_trigger)
        assert res["send_as"] == "vera"
        assert len(res["body"]) > 20
        assert res["cta"] in ("binary_yes_no", "open_ended", "multi_choice_slot")
        assert len(res["rationale"]) > 5
