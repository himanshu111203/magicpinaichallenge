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


class GymStrategy(BaseStrategy):
    """
    Vertical strategy for fitness centers, gyms, and yoga studios.
    Tone: Motivating, positive, results-driven, community-oriented.
    Handles trial followups, kids yoga programs, and membership renewals.
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
        owner = merchant.identity.owner_first_name or "Coach"

        # =========================================================================
        # 1. Customer-Facing Sends (On behalf of gym)
        # =========================================================================
        if is_customer and customer:
            c_name = customer.identity.name.split()[0] if customer.identity.name else "Champion"
            focus = getattr(customer.preferences, "training_focus", None) or "fitness goals"

            if family == TriggerFamily.RECALL_REMINDER or "trial" in trigger.kind:
                body = (
                    f"Hi {c_name}! Team {m_name} in {locality} here. "
                    f"Hope you enjoyed your trial session! Sticking to your {focus} routine builds momentum. "
                    f"Would you like us to activate your membership with a complimentary personal trainer assessment this week?"
                )
                cta = "binary_yes_no"
                rationale = "Post-trial onboarding conversion anchored to personal fitness goal and trainer assessment."
                return body, cta, rationale

            # Lapsed member winback
            body = (
                f"Hi {c_name}! We missed you at {m_name} this week. "
                f"Ready to restart your {focus} sessions? We've opened convenient morning and evening slots. "
                f"Shall we reserve your training spot tomorrow?"
            )
            cta = "binary_yes_no"
            rationale = "Member attendance retention prompt addressing workout lull before disengagement."
            return body, cta, rationale

        # =========================================================================
        # 2. Merchant-Facing Sends (Vera to Gym Owner)
        # =========================================================================

        # A. Planning Intent (Kids Yoga / Summer Camp)
        if family == TriggerFamily.PLANNING_INTENT or "yoga" in trigger.kind or "kids" in trigger.kind:
            body = (
                f"Hi {owner}! With school holidays approaching in {locality}, parents are actively searching for youth fitness and yoga activities. "
                f"Launching a 4-week \"Junior Fitness & Kids Yoga Workshop\" at {m_name} can enroll 15–20 children. "
                f"Shall Vera draft a promotion post for your Google Business listing?"
            )
            cta = "binary_yes_no"
            rationale = "Holiday youth fitness program monetization turning off-peak morning studio hours into group revenue."
            return body, cta, rationale

        # B. Performance & Member Retention
        if family == TriggerFamily.PERFORMANCE_MOVEMENT:
            views = merchant.performance.views
            body = (
                f"Hi {owner}! {m_name}'s Google listing received {views} views this month. "
                f"Gyms that display active member workout stories and certified trainer profiles convert 28% more trial walk-ins. "
                f"Would you like Vera to help spotlight your head trainer in a new post?"
            )
            cta = "binary_yes_no"
            rationale = "Trainer credential spotlighting to boost high-intent local search conversion."
            return body, cta, rationale

        # Default Merchant Outreach
        body = (
            f"Hi {owner}! Fitness and gym searches in {locality} peak every Monday morning. "
            f"Would you like to schedule a weekend Google update to capture prospective members setting their weekly goals?"
        )
        cta = "binary_yes_no"
        rationale = "Weekly cycle alignment leveraging habitual Monday fitness commitment wave."
        return body, cta, rationale
