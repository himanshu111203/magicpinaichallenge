from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
import threading
from typing import Optional

from src.models import (
    CustomerContext,
    MerchantContext,
    TriggerContext,
)
from src.services.conversation_store import TurnRecord, conversation_store


class SuppressionReason(str, Enum):
    """Enumeration of deterministic suppression causes."""
    NO_CONSENT = "customer_no_consent"
    NO_PHONE = "customer_no_phone"
    ANONYMOUS_WALKIN = "customer_anonymous_walkin"
    KEY_ALREADY_SUPPRESSED = "suppression_key_active"
    MERCHANT_TICK_LIMIT = "merchant_already_messaged_this_tick"
    TICK_ACTION_CAP = "tick_action_cap_reached"
    EXPIRED_TRIGGER = "trigger_expired"
    MERCHANT_INACTIVE_EXPIRED = "merchant_subscription_expired_no_winback"
    VERBATIM_BODY_REPEAT = "verbatim_body_repeat"


# Triggers permitted even if merchant subscription is expired
WINBACK_OR_RENEWAL_KINDS = frozenset({
    "renewal_due",
    "winback_eligible",
    "winback",
})

MAX_ACTIONS_PER_TICK = 20


@dataclass
class SuppressionDecision:
    """Outcome of a suppression evaluation."""
    suppressed: bool
    reason: Optional[SuppressionReason] = None
    details: Optional[str] = None

    @classmethod
    def allow(cls) -> SuppressionDecision:
        return cls(suppressed=False)

    @classmethod
    def suppress(cls, reason: SuppressionReason, details: str) -> SuppressionDecision:
        return cls(suppressed=True, reason=reason, details=details)


class SuppressionEngine:
    """
    Deterministic gatekeeper for message suppression, deduplication, consent compliance,
    and fatigue control.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._used_suppression_keys: set[str] = set()
        self._key_timestamps: dict[str, str] = {}
        self._tick_merchants: set[str] = set()
        self._tick_action_count: int = 0

    def reset(self) -> None:
        """Reset historical suppression keys and per-tick counters for a clean test run."""
        with self._lock:
            self._used_suppression_keys.clear()
            self._key_timestamps.clear()
            self._tick_merchants.clear()
            self._tick_action_count = 0

    def start_tick(self, now_iso: Optional[str] = None) -> None:
        """Initialize state for a new tick cycle."""
        with self._lock:
            self._tick_merchants.clear()
            self._tick_action_count = 0

    def check_trigger_suppression(
        self,
        trigger: TriggerContext,
        merchant: Optional[MerchantContext] = None,
        customer: Optional[CustomerContext] = None,
        now_iso: Optional[str] = None,
    ) -> SuppressionDecision:
        """
        Evaluate all suppression rules for a candidate trigger.
        Returns SuppressionDecision(suppressed=False) if allowed,
        or SuppressionDecision(suppressed=True, reason, details) if suppressed.
        """
        with self._lock:
            # 1. Global tick action cap (max 20 per tick)
            if self._tick_action_count >= MAX_ACTIONS_PER_TICK:
                return SuppressionDecision.suppress(
                    SuppressionReason.TICK_ACTION_CAP,
                    f"Reached max limit of {MAX_ACTIONS_PER_TICK} actions for this tick cycle",
                )

            # 2. Trigger expiration check
            if now_iso and trigger.expires_at and trigger.expires_at < now_iso:
                return SuppressionDecision.suppress(
                    SuppressionReason.EXPIRED_TRIGGER,
                    f"Trigger '{trigger.id}' expired at {trigger.expires_at} (current tick: {now_iso})",
                )

            # 3. Suppression key deduplication
            if trigger.suppression_key in self._used_suppression_keys:
                return SuppressionDecision.suppress(
                    SuppressionReason.KEY_ALREADY_SUPPRESSED,
                    f"Suppression key '{trigger.suppression_key}' was already acted on in this test window",
                )

            # 4. Per-merchant rate limit within tick (max 1 action per merchant per tick)
            if trigger.merchant_id in self._tick_merchants:
                return SuppressionDecision.suppress(
                    SuppressionReason.MERCHANT_TICK_LIMIT,
                    f"Merchant '{trigger.merchant_id}' already has an outreach scheduled in this tick",
                )

            # 5. Customer scope & consent compliance (Critical Gate)
            if trigger.scope == "customer" or customer is not None:
                if customer is None:
                    return SuppressionDecision.suppress(
                        SuppressionReason.NO_CONSENT,
                        f"Customer-scoped trigger '{trigger.id}' has no corresponding CustomerContext",
                    )

                if customer.is_anonymous_or_walkin:
                    return SuppressionDecision.suppress(
                        SuppressionReason.ANONYMOUS_WALKIN,
                        f"Customer '{customer.customer_id}' is an anonymous walk-in without a recorded profile or consent",
                    )

                if not customer.identity.phone_redacted:
                    return SuppressionDecision.suppress(
                        SuppressionReason.NO_PHONE,
                        f"Customer '{customer.customer_id}' has no usable phone contact",
                    )

                if not customer.has_valid_consent:
                    return SuppressionDecision.suppress(
                        SuppressionReason.NO_CONSENT,
                        f"Customer '{customer.customer_id}' does not have valid opt-in consent and scope",
                    )

            # 6. Merchant subscription lifecycle check
            if merchant is not None:
                is_expired = merchant.subscription.status == "expired"
                if is_expired and trigger.kind not in WINBACK_OR_RENEWAL_KINDS:
                    return SuppressionDecision.suppress(
                        SuppressionReason.MERCHANT_INACTIVE_EXPIRED,
                        f"Merchant '{merchant.merchant_id}' subscription is expired; regular trigger '{trigger.kind}' suppressed",
                    )

            # All suppression checks passed
            return SuppressionDecision.allow()

    def check_body_repetition(self, conversation_id: str, proposed_body: str) -> SuppressionDecision:
        """
        Check if the proposed body was sent previously in the same conversation.
        Protects against the -2 anti-repetition penalty.
        """
        if conversation_store.has_sent_body(conversation_id, proposed_body):
            return SuppressionDecision.suppress(
                SuppressionReason.VERBATIM_BODY_REPEAT,
                f"Verbatim body was already sent in conversation '{conversation_id}'",
            )
        return SuppressionDecision.allow()

    def record_action(
        self,
        trigger: TriggerContext,
        conversation_id: str,
        body: str,
        turn_number: int = 1,
        now_iso: Optional[str] = None,
        cta: Optional[str] = None,
        rationale: Optional[str] = None,
    ) -> None:
        """
        Commit an action to suppression tracking and conversation history.
        """
        with self._lock:
            # 1. Record suppression key
            self._used_suppression_keys.add(trigger.suppression_key)
            if now_iso:
                self._key_timestamps[trigger.suppression_key] = now_iso

            # 2. Record merchant in tick
            self._tick_merchants.add(trigger.merchant_id)
            self._tick_action_count += 1

            # 3. Record turn in conversation store
            conv = conversation_store.get(conversation_id)
            turn = TurnRecord(
                from_role="vera",
                body=body,
                ts=now_iso or "",
                turn_number=turn_number,
                cta=cta,
                rationale=rationale,
            )
            if conv is None:
                conversation_store.create_conversation(
                    conversation_id=conversation_id,
                    merchant_id=trigger.merchant_id,
                    customer_id=trigger.customer_id,
                    trigger_id=trigger.id,
                    suppression_key=trigger.suppression_key,
                    pending_trigger=trigger,
                    initial_turn=turn,
                )
            else:
                conv.add_turn(turn)
                conv.pending_trigger = trigger

    def is_key_suppressed(self, suppression_key: str) -> bool:
        """Check if a suppression key is currently active."""
        with self._lock:
            return suppression_key in self._used_suppression_keys

    def active_suppression_keys(self) -> set[str]:
        """Return a copy of all active suppression keys."""
        with self._lock:
            return set(self._used_suppression_keys)

    def clear(self) -> None:
        """Reset all suppression engine memory."""
        with self._lock:
            self._used_suppression_keys.clear()
            self._key_timestamps.clear()
            self._tick_merchants.clear()
            self._tick_action_count = 0


# Global singleton instance
suppression_engine = SuppressionEngine()
