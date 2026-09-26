from __future__ import annotations

from typing import Any, Optional, Union

from src.engine.signal_selector import SignalSelector
from src.engine.voice_validator import VoiceValidator
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.strategies.registry import get_strategy


def compose(
    category: Union[CategoryContext, dict[str, Any]],
    merchant: Union[MerchantContext, dict[str, Any]],
    trigger: Union[TriggerContext, dict[str, Any]],
    customer: Optional[Union[CustomerContext, dict[str, Any]]] = None,
) -> dict[str, Any]:
    """
    Pure composition function per challenge-brief.md §5 and challenge_analysis.md §B.
    Guarantees deterministic, grounded, category-correct copy with zero hallucinations.

    Returns:
        dict with keys:
        - "body": WhatsApp formatted text (no URLs, taboos neutralized)
        - "cta": Controlled vocabulary CTA
        - "send_as": "vera" | "merchant_on_behalf"
        - "suppression_key": str
        - "rationale": Grounded explanation of why this message, why now
    """
    # 1. Normalize dicts into Pydantic domain models if needed
    cat_model = CategoryContext.model_validate(category) if isinstance(category, dict) else category
    mer_model = MerchantContext.model_validate(merchant) if isinstance(merchant, dict) else merchant
    trg_model = TriggerContext.model_validate(trigger) if isinstance(trigger, dict) else trigger

    cust_model: Optional[CustomerContext] = None
    if customer is not None:
        cust_model = CustomerContext.model_validate(customer) if isinstance(customer, dict) else customer

    # 2. Determine send_as
    is_customer = cust_model is not None or trg_model.scope == "customer"
    send_as = "merchant_on_behalf" if is_customer else "vera"

    # 3. Extract grounded signals with anti-hallucination protection
    signals = SignalSelector.extract_signals(
        trigger=trg_model,
        merchant=mer_model,
        category=cat_model,
        customer=cust_model,
    )

    # 4. Route to category vertical strategy
    strategy = get_strategy(cat_model.slug)
    raw_body, raw_cta, rationale = strategy.compose_message(
        signals=signals,
        category=cat_model,
        merchant=mer_model,
        trigger=trg_model,
        customer=cust_model,
    )

    # 5. Sanitize body against category voice rules, taboos, and disallowed URLs
    body = VoiceValidator.sanitize_body(raw_body, cat_model)
    cta = VoiceValidator.validate_cta(raw_cta)

    # 6. Echo / derive suppression key
    suppression_key = trg_model.suppression_key

    return {
        "body": body,
        "cta": cta,
        "send_as": send_as,
        "suppression_key": suppression_key,
        "rationale": rationale,
    }
