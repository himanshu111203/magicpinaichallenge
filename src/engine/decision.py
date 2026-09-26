from __future__ import annotations

from dataclasses import dataclass, field
import threading
import time
from typing import Any, Optional

from src.engine.semantic_family import TriggerFamily, classify_trigger_family
from src.engine.signal_selector import CandidateSignalBundle, SignalSelector
from src.engine.suppression import (
    MAX_ACTIONS_PER_TICK,
    SuppressionDecision,
    SuppressionReason,
    suppression_engine,
)
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.context_store import context_store


@dataclass
class RankedCandidate:
    """A fully contextualized and ranked candidate action ready for composition or tick send."""
    trigger: TriggerContext
    merchant: MerchantContext
    category: CategoryContext
    customer: Optional[CustomerContext]
    semantic_family: TriggerFamily
    signals: CandidateSignalBundle
    priority_score: float
    score_reasons: list[str] = field(default_factory=list)
    suppression_decision: SuppressionDecision = field(default_factory=SuppressionDecision.allow)

    def to_tick_action(self, conversation_id_prefix: str = "conv") -> dict[str, Any]:
        """
        Produce a spec-compliant wire action dict for POST /v1/tick.
        Guarantees all required fields per challenge-testing-brief §2.2 & api-call-examples.md.
        """
        from src.engine.composer import compose

        conv_id = f"{conversation_id_prefix}_{self.trigger.id}_{int(time.time())}"
        composed = compose(
            category=self.category,
            merchant=self.merchant,
            trigger=self.trigger,
            customer=self.customer,
        )

        return {
            "conversation_id": conv_id,
            "merchant_id": self.merchant.merchant_id,
            "customer_id": self.customer.customer_id if self.customer else None,
            "send_as": composed["send_as"],
            "trigger_id": self.trigger.id,
            "template_name": f"tpl_{self.semantic_family.value}",
            "template_params": [f.field for f in self.signals.grounded_facts[:5]],
            "body": composed["body"],
            "cta": composed["cta"],
            "suppression_key": composed["suppression_key"],
            "rationale": composed["rationale"],
        }



class DecisionEngine:
    """
    Deterministic candidate selection, suppression pre-flight gatekeeper,
    and priority ranking engine for Vera.
    """

    MIN_SCORE_THRESHOLD = 25.0

    def __init__(self) -> None:
        self._lock = threading.RLock()

    def evaluate_candidate(
        self,
        trigger: TriggerContext,
        now_iso: Optional[str] = None,
    ) -> Optional[RankedCandidate]:
        """
        Evaluate a single candidate trigger against stored merchant, category,
        and customer contexts. Returns a RankedCandidate if eligible, or None if suppressed/invalid.
        """
        # 1. Resolve merchant context
        merchant = context_store.get_model("merchant", trigger.merchant_id)
        if not isinstance(merchant, MerchantContext):
            return None

        # 2. Resolve category context
        category = context_store.get_model("category", merchant.category_slug)
        if not isinstance(category, CategoryContext):
            return None

        # 3. Resolve customer context (if customer-scoped)
        customer: Optional[CustomerContext] = None
        if trigger.scope == "customer" or trigger.customer_id:
            cid = trigger.customer_id
            if cid:
                c_model = context_store.get_model("customer", cid)
                if isinstance(c_model, CustomerContext):
                    customer = c_model
                else:
                    return None  # Missing customer context for customer-scoped trigger
            else:
                return None

        # 4. Suppression Engine Pre-Flight Gate
        supp_decision = suppression_engine.check_trigger_suppression(
            trigger=trigger,
            merchant=merchant,
            customer=customer,
            now_iso=now_iso,
        )
        if supp_decision.suppressed:
            return None

        # 5. Semantic Family Classification
        family = classify_trigger_family(trigger.kind)

        # 6. Grounded Signal Extraction
        signals = SignalSelector.extract_signals(
            trigger=trigger,
            merchant=merchant,
            category=category,
            customer=customer,
        )

        # 7. Deterministic Priority Scoring
        score = 0.0
        score_reasons: list[str] = []

        # A. Base Urgency Weight (urgency 1-5 -> 15-75 pts)
        urgency_pts = trigger.urgency * 15.0
        score += urgency_pts
        score_reasons.append(f"base_urgency_{trigger.urgency}(+{urgency_pts:.0f})")

        # B. Subscription Lifecycle Priorities
        if merchant.subscription.status == "expired":
            if trigger.kind in ("winback_eligible", "winback"):
                score += 25.0
                score_reasons.append("winback_priority(+25)")
        elif merchant.subscription.status == "active":
            days = merchant.subscription.days_remaining
            if days is not None and days <= 7 and trigger.kind in ("renewal_due", "renewal"):
                score += 35.0
                score_reasons.append(f"renewal_due_{days}d(+35)")

        # C. Direct Customer Outreach Impact
        if customer is not None:
            score += 10.0
            score_reasons.append("customer_direct_outreach(+10)")

        # D. Grounding & Payload Richness
        if not trigger.is_placeholder_payload:
            score += 10.0
            score_reasons.append("rich_seed_payload(+10)")
        elif signals.has_strong_signals:
            score += 5.0
            score_reasons.append("grounded_merchant_signals(+5)")
        else:
            # Low-value placeholder penalty to prevent unmotivated spam
            score -= 10.0
            score_reasons.append("thin_placeholder_penalty(-10)")

        # E. Expiration Proximity
        if now_iso and trigger.expires_at:
            # If trigger expires within ~2 days of now, give a small boost
            if trigger.expires_at > now_iso:
                score += 5.0
                score_reasons.append("approaching_expiry(+5)")

        # F. Minimum threshold check (Anti-spam / Restraint principle)
        if score < self.MIN_SCORE_THRESHOLD:
            return None

        return RankedCandidate(
            trigger=trigger,
            merchant=merchant,
            category=category,
            customer=customer,
            semantic_family=family,
            signals=signals,
            priority_score=score,
            score_reasons=score_reasons,
            suppression_decision=supp_decision,
        )

    def select_candidates(
        self,
        available_trigger_ids: Optional[list[str]] = None,
        now_iso: Optional[str] = None,
    ) -> list[RankedCandidate]:
        """
        Evaluate candidate triggers, enforce 1 action per merchant per tick,
        rank by priority score, and cap at MAX_ACTIONS_PER_TICK (20).
        """
        with self._lock:
            # 1. Determine trigger pool
            candidate_triggers: list[TriggerContext] = []
            if available_trigger_ids is not None:
                for tid in available_trigger_ids:
                    t_model = context_store.get_model("trigger", tid)
                    if isinstance(t_model, TriggerContext):
                        candidate_triggers.append(t_model)
            else:
                # Fallback to all loaded triggers
                all_trigs = context_store.get_models_by_scope("trigger")
                candidate_triggers = [t for t in all_trigs if isinstance(t, TriggerContext)]

            if not candidate_triggers:
                return []

            # 2. Evaluate each trigger
            valid_candidates: list[RankedCandidate] = []
            for trg in candidate_triggers:
                cand = self.evaluate_candidate(trg, now_iso=now_iso)
                if cand is not None:
                    valid_candidates.append(cand)

            if not valid_candidates:
                return []

            # 3. Enforce 1 action per merchant per tick (FAQ §14)
            # Group by merchant_id and select the single highest-scoring candidate
            by_merchant: dict[str, RankedCandidate] = {}
            for cand in valid_candidates:
                mid = cand.merchant.merchant_id
                if mid not in by_merchant or cand.priority_score > by_merchant[mid].priority_score:
                    by_merchant[mid] = cand

            deduped_candidates = list(by_merchant.values())

            # 4. Sort globally by priority score descending
            deduped_candidates.sort(key=lambda c: c.priority_score, reverse=True)

            # 5. Cap at MAX_ACTIONS_PER_TICK (20 actions per tick)
            selected = deduped_candidates[:MAX_ACTIONS_PER_TICK]

            return selected


# Global singleton instance
decision_engine = DecisionEngine()
