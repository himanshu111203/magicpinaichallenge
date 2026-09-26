from __future__ import annotations

from typing import Optional

from src.engine.semantic_family import TriggerFamily
from src.engine.signal_selector import CandidateSignalBundle
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.strategies.base import BaseStrategy


class GeneralStrategy(BaseStrategy):
    """Fallback strategy for unseen categories or general nudges."""

    def compose_message(
        self,
        signals: CandidateSignalBundle,
        category: CategoryContext,
        merchant: MerchantContext,
        trigger: TriggerContext,
        customer: Optional[CustomerContext] = None,
    ) -> tuple[str, str, str]:
        is_customer = customer is not None or trigger.scope == "customer"
        m_name = merchant.identity.name
        locality = merchant.identity.locality
        owner = merchant.identity.owner_first_name or "there"

        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "there"
            last_srv = signals.customer_last_service or "visit"
            body = (
                f"Hi {c_name}! This is {m_name} in {locality}. "
                f"Checking in following your recent {last_srv}. "
                f"Would you like us to reserve a convenient slot for you this week?"
            )
            cta = "binary_yes_no"
            rationale = "Customer relationship follow-up with direct booking reservation ask."
            return body, cta, rationale

        # Merchant facing
        if signals.digest_item_title and signals.digest_item_source:
            body = (
                f"Hi {owner}! Fresh industry update from {signals.digest_item_source}: "
                f"\"{signals.digest_item_title}\". "
                f"Shall Vera prepare a brief summary post on your Google Business Profile for {m_name}?"
            )
            cta = "binary_yes_no"
            rationale = "Industry digest briefing providing professional social proof on Google Business."
            return body, cta, rationale

        if signals.active_offer_title:
            body = (
                f"Hi {owner}! Your active offer \"{signals.active_offer_title}\" is ready to feature for {m_name}. "
                f"Would you like Vera to promote it on Google to attract more inquiries this week?"
            )
            cta = "binary_yes_no"
            rationale = "Active merchant offer promotion on Google Business profile."
            return body, cta, rationale

        body = (
            f"Hi {owner}! Vera checked {m_name}'s local discovery trends in {locality}. "
            f"Would you like a quick review of your search performance and customer engagement this week?"
        )
        cta = "binary_yes_no"
        rationale = "Low-friction performance review invitation to drive merchant engagement."
        return body, cta, rationale
