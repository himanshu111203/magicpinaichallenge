from __future__ import annotations

import re
from typing import Any, Optional

from src.engine.composer import compose
from src.models import CategoryContext, CustomerContext, MerchantContext, TriggerContext
from src.services.context_store import context_store
from src.services.conversation_store import TurnRecord, conversation_store


class ReplyHandler:
    """
    Handles inbound messages for POST /v1/reply.
    Enforces immediate intent transition to action mode, WhatsApp Business
    auto-reply filtering, hostility handling, and conversation lifecycle states.
    """

    AUTO_REPLY_PATTERNS = [
        r"thank\s+you\s+for\s+contacting",
        r"our\s+team\s+will\s+respond",
        r"automated\s+response",
        r"auto-?reply",
        r"we\s+are\s+currently\s+unavailable",
        r"will\s+get\s+back\s+to\s+you",
        r"thanks\s+for\s+reaching\s+out",
        r"we\s+will\s+respond\s+shortly",
    ]

    HOSTILE_PATTERNS = [
        r"\bstop\b",
        r"\bunsubscribe\b",
        r"\bspam\b",
        r"\buseless\b",
        r"\bleave\s+me\s+alone\b",
        r"\bnot\s+interested\b",
        r"\bdon'?t\s+message\b",
        r"\bremove\s+me\b",
        r"\bblock\b",
    ]

    COMMITMENT_PATTERNS = [
        r"\bok\b",
        r"\bokay\b",
        r"let'?s\s+do\s+it",
        r"what'?s\s+next",
        r"\byes\b",
        r"\bsure\b",
        r"\bproceed\b",
        r"\bconfirm\b",
        r"\bgo\s+ahead\b",
        r"\bdraft\b",
        r"\bdo\s+it\b",
        r"\bsend\s+it\b",
        r"\bagreed\b",
    ]

    DELAY_PATTERNS = [
        r"\blater\b",
        r"\bbusy\b",
        r"call\s+me\s+tomorrow",
        r"give\s+me\s+some\s+time",
        r"in\s+(?:the\s+)?evening",
        r"tomorrow",
    ]

    @classmethod
    def handle_reply(
        cls,
        conversation_id: str,
        merchant_id: Optional[str],
        customer_id: Optional[str],
        from_role: str,
        message: str,
        received_at: str,
        turn_number: int,
        category_context: Optional[CategoryContext] = None,
        merchant_context: Optional[MerchantContext] = None,
        customer_context: Optional[CustomerContext] = None,
        trigger_context: Optional[TriggerContext] = None,
    ) -> dict[str, Any]:
        """
        Process inbound reply and return wire-compliant response:
        - {"action": "send", "body": "...", "cta": "...", "rationale": "..."}
        - {"action": "wait", "wait_seconds": N, "rationale": "..."}
        - {"action": "end", "rationale": "..."}
        """
        msg_clean = message.strip()
        msg_lower = msg_clean.lower()

        # Track conversation turn
        conv = conversation_store.get(conversation_id)
        if conv is None:
            conv = conversation_store.create_conversation(
                conversation_id=conversation_id,
                merchant_id=merchant_id or "m_unknown",
                customer_id=customer_id,
            )

        conv.add_turn(TurnRecord(
            from_role=from_role or "merchant",
            body=msg_clean,
            ts=received_at,
            turn_number=turn_number,
        ))

        trigger_context = trigger_context or conv.pending_trigger
        merchant_context = merchant_context or (
            context_store.get_model("merchant", merchant_id) if merchant_id else None
        )
        if category_context is None and merchant_context:
            category_context = context_store.get_model("category", merchant_context.category_slug)
        if customer_context is None and trigger_context and trigger_context.customer_id:
            customer_context = context_store.get_model("customer", trigger_context.customer_id)

        # Look up merchant name for grounding
        merchant_name = "your business"
        if isinstance(merchant_context, MerchantContext):
            merchant_name = merchant_context.identity.name

        # =========================================================================
        # 1. Hostile / Opt-out Detection (Phase 12)
        # =========================================================================
        for pat in cls.HOSTILE_PATTERNS:
            if re.search(pat, msg_lower):
                conversation_store.end_conversation(conversation_id)
                return {
                    "action": "end",
                    "body": "Understood. I will stop outreach as requested.",
                    "cta": "none",
                    "rationale": "Merchant requested to stop outreach or expressed dissatisfaction; conversation ended immediately to honor preference.",
                }

        # =========================================================================
        # 2. WhatsApp Business Canned Auto-Reply Detection (Phase 11)
        # =========================================================================
        is_auto_reply = any(re.search(pat, msg_lower) for pat in cls.AUTO_REPLY_PATTERNS)
        if is_auto_reply:
            # Check turn number / recurrence
            if turn_number <= 2:
                # First automated greeting: wait or end to avoid bot loop
                conversation_store.end_conversation(conversation_id)
                return {
                    "action": "end",
                    "body": "Automated reply detected; no campaign message was sent.",
                    "cta": "none",
                    "rationale": "WhatsApp Business canned auto-reply greeting detected; ending conversation cleanly per protocol.",
                }
            else:
                conversation_store.end_conversation(conversation_id)
                return {
                    "action": "end",
                    "body": "Automated reply detected; no campaign message was sent.",
                    "cta": "none",
                    "rationale": "Repeated WhatsApp Business canned auto-reply detected; ending conversation.",
                }

        # =========================================================================
        # 3. Deferral / Delay Detection (Phase 13)
        # =========================================================================
        for pat in cls.DELAY_PATTERNS:
            if re.search(pat, msg_lower):
                return {
                    "action": "wait",
                    "wait_seconds": 3600,
                    "body": "Understood. I will pause outreach as requested.",
                    "cta": "none",
                    "rationale": "Merchant asked to reconnect later; set wait state for 1 hour.",
                }

        # =========================================================================
        # 4. Intent Commitment Transition (Phase 10 — Must Switch to ACTION Mode)
        # Strictly uses ACTION words: ["done", "sending", "draft", "here", "confirm", "proceed", "next"]
        # Strictly avoids QUALIFYING words: ["would you", "do you", "can you tell", "what if", "how about"]
        # =========================================================================
        is_commitment = any(re.search(pat, msg_lower) for pat in cls.COMMITMENT_PATTERNS)
        if is_commitment:
            if not all((category_context, merchant_context, trigger_context)):
                return {
                    "action": "wait",
                    "wait_seconds": 0,
                    "body": "I don't have a verified outreach trigger selected in this conversation, so I haven't drafted or sent a message. Please select a current signal or active offer first.",
                    "cta": "clarify",
                    "rationale": "Acceptance received without the context required to compose grounded outreach; no message was fabricated or sent.",
                }

            composed = compose(
                category=category_context,
                merchant=merchant_context,
                trigger=trigger_context,
                customer=customer_context if trigger_context.scope == "customer" else None,
            )
            body = composed["body"]
            # Record turn in conversation store
            conv.add_turn(TurnRecord(
                from_role="vera",
                body=body,
                ts=received_at,
                turn_number=turn_number + 1,
            ))
            return {
                "action": "send",
                "body": body,
                "cta": composed["cta"],
                "rationale": f"Accepted the selected {trigger_context.kind} trigger and composed outreach from current merchant, category, and trigger context.",
            }

        # =========================================================================
        # 5. Unmatched Reply (do not imply that an unrequested action was taken)
        # =========================================================================
        return {
            "action": "wait",
            "wait_seconds": 0,
            "body": "I couldn't match that reply to a current outreach action, so I haven't drafted or sent anything.",
            "cta": "clarify",
            "rationale": "Reply did not match an opt-out, deferral, auto-reply, or commitment action.",
        }
