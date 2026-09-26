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


class PharmacyStrategy(BaseStrategy):
    """
    Vertical strategy for retail and community pharmacies.
    Tone: Caring, reliable, compliant, health-supportive, non-prescriptive.
    Strictly avoids diagnostic claims or unverified health advice.
    Focuses on chronic refills, home delivery, and seasonal essentials.
    """

    def compose_message(
        self,
        signals: CandidateSignalBundle,
        category: CategoryContext,
        merchant: MerchantContext,
        trigger: TriggerContext,
        customer: Optional[CustomerContext] = None,
    ) -> tuple[str, str, str]:
        family = signals.semantic_family
        is_customer = customer is not None or trigger.scope == "customer"
        m_name = merchant.identity.name
        locality = merchant.identity.locality
        owner = merchant.identity.owner_first_name or "Pharmacist"

        # =========================================================================
        # 1. Customer-Facing Sends (On behalf of pharmacy)
        # =========================================================================
        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "there"

            if family == TriggerFamily.RECALL_REMINDER or "refill" in trigger.kind:
                body = (
                    f"Hi {c_name}, {m_name} ({locality}) here. "
                    f"Checking in on your monthly regular health and wellness refills. "
                    f"To ensure you don't run out, we can arrange prompt home delivery or keep your pack ready for pickup. "
                    f"Would you like us to prepare your regular refill for delivery today?"
                )
                cta = "binary_yes_no"
                rationale = "Chronic medication replenishment reminder ensuring adherence and home delivery convenience."
                return body, cta, rationale

            # General customer health support
            body = (
                f"Hi {c_name}, {m_name} here. We have updated our local doorstep delivery schedule in {locality}. "
                f"Do you need any household health essentials or regular supplies delivered this week?"
            )
            cta = "binary_yes_no"
            rationale = "Local doorstep delivery outreach supporting recurring household pharmacy essentials."
            return body, cta, rationale

        # =========================================================================
        # 2. Merchant-Facing Sends (Vera to Pharmacist)
        # =========================================================================

        # A. Seasonal Demand Shift (e.g. Summer hydration / Monsoon care)
        if family == TriggerFamily.SEASONAL_EVENT or "summer" in trigger.kind or "demand" in trigger.kind:
            body = (
                f"Hi {owner}! Rising temperatures in {locality} are driving high demand for hydration essentials, ORS, and sun care. "
                f"Highlighting quick home delivery for summer essentials on Google can increase daily order volume by 25%. "
                f"Shall Vera post a summer wellness delivery update on {m_name}'s profile?"
            )
            cta = "binary_yes_no"
            rationale = "Seasonal weather shift capitalization driving prompt OTC hydration and delivery inquiries."
            return body, cta, rationale

        # B. Performance & Local Delivery Awareness
        if family == TriggerFamily.PERFORMANCE_MOVEMENT:
            calls = merchant.performance.calls
            body = (
                f"Hi {owner}! {m_name} received {calls} inquiry calls on Google Business in the past 30 days. "
                f"Pinning a clear notice that you offer 'Same-Day Home Delivery in {locality}' turns phone inquiries into immediate orders. "
                f"Would you like Vera to draft a home delivery highlight post?"
            )
            cta = "binary_yes_no"
            rationale = "Grounded call inquiry conversion leveraging local same-day delivery assurance."
            return body, cta, rationale

        # Default Merchant Outreach
        body = (
            f"Hi {owner}! Local medicine delivery searches in {locality} remain strong. "
            f"Would you like Vera to share a quick update on your Google profile confirming active pharmacy and delivery hours?"
        )
        cta = "binary_yes_no"
        rationale = "Routine pharmacy operational status confirmation driving local walk-ins and phone orders."
        return body, cta, rationale
