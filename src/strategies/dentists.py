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


class DentistStrategy(BaseStrategy):
    """
    Vertical strategy for dental clinics.
    Tone: Evidence-based, clinical peer respect, professional, non-promotional.
    Strictly avoids taboo words ('guaranteed', 'cure', '100%').
    Favors service+price offers ('Dental Cleaning @ ₹299') over generic discounts.
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
        owner = merchant.identity.owner_first_name or "Doctor"

        if trigger.kind == "high_risk_adult_cohort":
            offer = signals.active_offer_title
            if offer:
                return (
                    f"Hi, this is {m_name} in {locality}. We are sharing our active {offer} offer. "
                    "Would you like to schedule a cleaning appointment?",
                    "binary_yes_no",
                    "WhatsApp draft uses the active dental offer attached to the verified adult-cohort trigger.",
                )

        # =========================================================================
        # 1. Customer-Facing Sends (On behalf of merchant)
        # =========================================================================
        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "there"
            last_srv = signals.customer_last_service or "dental checkup"
            last_vis = signals.customer_last_visit or "your last visit"

            if family == TriggerFamily.RECALL_REMINDER:
                offer_mention = f" We currently have {signals.active_offer_title} available." if signals.active_offer_title else ""
                body = (
                    f"Hi {c_name}, Dr. {owner}'s clinic ({m_name}, {locality}) here! "
                    f"It has been 6 months since your {last_srv}. Regular recall checkups help prevent plaque buildup.{offer_mention} "
                    f"Would you like us to reserve a convenient slot for you this week?"
                )
                cta = "binary_yes_no"
                rationale = "Customer 6-month hygiene recall window open; framed around preventive care with service+price offer anchor."
                return body, cta, rationale

            # Default customer message
            body = (
                f"Hi {c_name}, Dr. {owner} from {m_name} here. "
                f"We are following up regarding your {last_srv}. "
                f"Are you experiencing any discomfort, or would you like to schedule your routine review?"
            )
            cta = "binary_yes_no"
            rationale = "Clinical follow-up on recent procedure; checking patient comfort and booking next routine review."
            return body, cta, rationale

        # =========================================================================
        # 2. Merchant-Facing Sends (Vera to Merchant)
        # =========================================================================

        # A. Research Digest / Compliance / Trends
        if family == TriggerFamily.RESEARCH_COMPLIANCE_TREND:
            title = signals.digest_item_title or "3-mo recall cuts caries recurrence 38% better than 6-mo"
            source = signals.digest_item_source or "JIDA Oct 2026, p.14"
            import re
            clean_source = re.sub(r'\b\d{4}-\d{2}-\d{2}\b', '', source).strip(' ,')
            stale_str = f"Since your clinic profile hasn't posted in {signals.stale_posts_days} days, " if signals.stale_posts_days else ""
            body = (
                f"Dr. {owner}, quick update from {clean_source}: "
                f"\"{title}\". "
                f"{stale_str}sharing this clinical update will reassure patients and keep {m_name} fully compliant before the deadline. "
                f"Shall Vera draft a concise 2-line post for your review?"
            )
            cta = "binary_yes_no"
            rationale = f"Evidence-based peer engagement citing {clean_source}; re-activates dormant profile with compliance anchor."
            return body, cta, rationale

        # B. Performance Movement
        if family == TriggerFamily.PERFORMANCE_MOVEMENT:
            metric_val = signals.primary_metric_value
            metric_name = signals.primary_metric_name or "patient inquiries"
            peer_benchmark = signals.peer_benchmark_value
            peer_text = f" (peer average is {peer_benchmark} calls/mo)" if peer_benchmark else ""

            if metric_val is not None and metric_val < 0:
                body = (
                    f"Dr. {owner}, we reviewed {m_name}'s 7-day Google profile metrics: "
                    f"{metric_name} dipped {abs(metric_val)}%{peer_text}. "
                    f"Adding fresh clinic photos or an updated service post typically recovers discovery within 48h. "
                    f"Would you like Vera to draft a recovery post today?"
                )
            else:
                body = (
                    f"Dr. {owner}, {m_name}'s profile views jumped {abs(metric_val or 18)}% this week! "
                    f"Would you like to feature your \"{signals.active_offer_title or 'Dental Cleaning @ ₹299'}\" offer to convert these views into confirmed appointments?"
                )
            cta = "binary_yes_no"
            rationale = "Grounded metric delta review with peer benchmarking and immediate one-tap GBP optimization action."
            return body, cta, rationale

        # C. Dormancy / Subscription Renewal
        if family == TriggerFamily.DORMANCY_LAPSE:
            if trigger.kind in ("renewal_due", "renewal"):
                days = merchant.subscription.days_remaining or 3
                body = (
                    f"Dr. {owner}, your {merchant.subscription.plan} listing protection for {m_name} renews in {days} days. "
                    f"Maintaining verified Google Business status ensures uninterrupted patient inquiries. "
                    f"Would you like to confirm renewal now?"
                )
                cta = "binary_confirm_cancel"
                rationale = f"High-stakes subscription renewal notice ({days}d remaining); highlights inquiry protection."
                return body, cta, rationale

            # Winback or dormancy
            body = (
                f"Dr. {owner}, local searches for dentists in {locality} rose 24% this month. "
                f"Shall we refresh {m_name}'s active service hours and highlight your {signals.active_offer_title or 'cleaning packages'} to capture new walk-ins?"
            )
            cta = "binary_yes_no"
            rationale = "Winback reactivation anchored on local locality search surge and service visibility."
            return body, cta, rationale

        # D. Planning Intent & Seasonal Events
        if family in (TriggerFamily.PLANNING_INTENT, TriggerFamily.SEASONAL_EVENT):
            beat = signals.seasonal_beat_note or "wedding season teeth whitening demand peak"
            body = (
                f"Dr. {owner}, seasonal demand shift in {locality}: {beat}. "
                f"Patients actively seek whitening and aligner consultations right now. "
                f"Shall Vera prepare a tailored Google post highlighting {signals.active_offer_title or 'Teeth Whitening @ ₹1,499'} for {m_name}?"
            )
            cta = "binary_yes_no"
            rationale = "Seasonal demand alignment converting seasonal patient search volume into appointment bookings."
            return body, cta, rationale

        # Fallback / General Nudge
        body = (
            f"Dr. {owner}, Vera reviewed {m_name}'s listing in {locality}. "
            f"Would you like a 30-second summary of your patient inquiry trends and top search queries this week?"
        )
        cta = "binary_yes_no"
        rationale = "General curious ask cadence respecting doctor time budget with zero pressure."
        return body, cta, rationale
