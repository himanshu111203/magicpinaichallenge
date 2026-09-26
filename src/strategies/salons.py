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


class SalonStrategy(BaseStrategy):
    """
    Vertical strategy for beauty salons and spas.
    Tone: Warm, stylish, encouraging, service+price oriented.
    Avoids medical claims (e.g., claiming to 'cure' hair conditions).
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
        # 1. Customer-Facing Sends (On behalf of salon)
        # =========================================================================
        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "there"
            last_srv = signals.customer_last_service or "hair styling"
            stylist = getattr(customer.preferences, "preferred_stylist", None)
            stylist_mention = f" with {stylist}" if stylist else ""

            if family == TriggerFamily.RECALL_REMINDER or "wedding" in trigger.kind:
                offer_text = f" We're currently featuring {signals.active_offer_title}." if signals.active_offer_title else ""
                body = (
                    f"Hi {c_name}! It's been about 6 weeks since your {last_srv} at {m_name}, {locality}. "
                    f"Regular touch-ups keep your look fresh and healthy.{offer_text} "
                    f"Would you like us to hold a slot{stylist_mention} for you this Friday or Saturday?"
                )
                cta = "multi_choice_slot"
                rationale = "Routine salon maintenance cycle (6-week recall); anchors preferred stylist and slot flexibility."
                return body, cta, rationale

            # General appointment or follow-up
            body = (
                f"Hi {c_name}! {m_name} here. Just checking in after your {last_srv}. "
                f"How are you loving your new style? Let us know if you'd like to book your next session!"
            )
            cta = "open_ended"
            rationale = "Post-service satisfaction touchpoint strengthening client retention and re-booking."
            return body, cta, rationale

        # =========================================================================
        # 2. Merchant-Facing Sends (Vera to Salon Owner)
        # =========================================================================

        # A. Performance & Review Themes
        if family == TriggerFamily.PERFORMANCE_MOVEMENT or family == TriggerFamily.MILESTONE:
            theme = signals.review_theme_name or "stylist expertise"
            quote = f" (\"{signals.review_theme_quote}\")" if signals.review_theme_quote else ""
            body = (
                f"Hi {owner}! Customers frequently praise {theme}{quote} on {m_name}'s Google listing. "
                f"Highlighting client reviews brings 30% more bridal and styling bookings. "
                f"Shall Vera create a showcase post celebrating your team's work today?"
            )
            cta = "binary_yes_no"
            rationale = "Social proof amplification converting genuine positive review sentiment into new customer bookings."
            return body, cta, rationale

        # B. Dormancy & Off-Peak Fill
        if family == TriggerFamily.DORMANCY_LAPSE:
            offer = signals.active_offer_title or "Haircut @ ₹99"
            body = (
                f"Hi {owner}! Tuesday and Wednesday afternoons have open chairs at {m_name}. "
                f"Promoting a limited off-peak slot for \"{offer}\" can fill 4–6 empty slots. "
                f"Would you like Vera to post this on your Google profile?"
            )
            cta = "binary_yes_no"
            rationale = "Off-peak capacity utilization targeting weekday salon lull with service+price promotion."
            return body, cta, rationale

        # C. Seasonal Events & Trends
        if family in (TriggerFamily.SEASONAL_EVENT, TriggerFamily.PLANNING_INTENT):
            beat = signals.seasonal_beat_note or "bridal packages and festival styling peak"
            body = (
                f"Hi {owner}! Wedding and party styling searches in {locality} are spiking now: {beat}. "
                f"Shall we publish {m_name}'s bridal and makeover packages on Google to capture weekend bookings?"
            )
            cta = "binary_yes_no"
            rationale = "Seasonal bridal demand capitalization driving high-ticket package inquiries."
            return body, cta, rationale

        # Default Merchant Outreach
        body = (
            f"Hi {owner}! Vera checked {m_name}'s local Google visibility in {locality}. "
            f"Would you like to review 3 quick tips to attract more walk-ins this weekend?"
        )
        cta = "binary_yes_no"
        rationale = "Low-friction weekend walk-in optimization prompt."
        return body, cta, rationale
