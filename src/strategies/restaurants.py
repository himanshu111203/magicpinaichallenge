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


class RestaurantStrategy(BaseStrategy):
    """
    Vertical strategy for restaurants, cafes, and eateries.
    Tone: Warm, appetizing, focused on table turns, corporate orders, and seasonal events.
    Handles corporate thali planning, match screenings, and off-peak dining.
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
        owner = merchant.identity.owner_first_name or "there"

        # =========================================================================
        # 1. Customer-Facing Sends (On behalf of restaurant)
        # =========================================================================
        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "foodie"
            fav_dish = getattr(customer.relationship, "favourite_dish", None) or "favourite meal"

            body = (
                f"Hi {c_name}! Craving your {fav_dish} from {m_name}, {locality}? "
                f"We're setting up fresh tables for lunch and dinner service this week. "
                f"Would you like us to reserve a table for you and your friends this evening?"
            )
            cta = "binary_yes_no"
            rationale = "Customer patronage winback leveraging favorite dish recall and prompt dining reservation."
            return body, cta, rationale

        # =========================================================================
        # 2. Merchant-Facing Sends (Vera to Restaurateur)
        # =========================================================================

        # A. Planning Intent (Corporate Thali / Catering)
        if family == TriggerFamily.PLANNING_INTENT or "thali" in trigger.kind:
            offer = signals.active_offer_title or "Executive Lunch Thali @ ₹199"
            body = (
                f"Hi {owner}! Nearby tech parks and corporate offices in {locality} are ordering daily team lunches. "
                f"Promoting a dedicated \"{offer}\" can bring 20–30 steady weekday lunch orders. "
                f"Shall Vera post a corporate lunch feature on your Google Business Profile today?"
            )
            cta = "binary_yes_no"
            rationale = "B2B weekday lunch volume capture targeting local office clusters with structured thali offer."
            return body, cta, rationale

        # B. Seasonal Events / IPL Match
        if family == TriggerFamily.SEASONAL_EVENT or "ipl" in trigger.kind or "match" in trigger.kind:
            body = (
                f"Hi {owner}! Big match scheduled today! Evening dine-in searches in {locality} surge 40% on match nights. "
                f"Shall we publish a quick post highlighting live match screening and snack combos at {m_name}?"
            )
            cta = "binary_yes_no"
            rationale = "Real-time sporting event tie-in driving dine-in footfall during peak match broadcast hours."
            return body, cta, rationale

        # C. Performance & Reviews
        if family == TriggerFamily.PERFORMANCE_MOVEMENT:
            calls = merchant.performance.calls
            body = (
                f"Hi {owner}! {m_name} received {calls} direct inquiry calls on Google in the last 30 days. "
                f"Updating your weekend specials and dining menu photos helps turn 35% more callers into reservations. "
                f"Would you like Vera to help refresh your menu posts?"
            )
            cta = "binary_yes_no"
            rationale = "Grounded call volume review encouraging photo and menu updates to maximize caller conversion."
            return body, cta, rationale

        # Default Merchant Outreach
        body = (
            f"Hi {owner}! Weekend dining searches in {locality} start climbing Thursday afternoons. "
            f"Would you like to feature a chef's special post for {m_name} to capture weekend table reservations?"
        )
        cta = "binary_yes_no"
        rationale = "Pre-weekend table booking mobilization targeting prime dining decision window."
        return body, cta, rationale
