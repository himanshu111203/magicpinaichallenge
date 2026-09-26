"""
Multi-turn conversation handler per challenge-brief.md §7.4.
Demonstrates multi-turn handling replying to merchant/customer responses.
"""

from __future__ import annotations

from typing import Any, Union

from src.engine.reply_handler import ReplyHandler


def respond(state: Union[dict[str, Any], Any], user_message: str) -> dict[str, Any]:
    """
    Given the conversation state + latest user message, produce the reply.
    Implements immediate intent transition to action mode, auto-reply filtering,
    and hostile opt-out de-escalation.
    """
    conv_id = state.get("conversation_id", "conv_default") if isinstance(state, dict) else getattr(state, "conversation_id", "conv_default")
    mid = state.get("merchant_id") if isinstance(state, dict) else getattr(state, "merchant_id", None)
    cid = state.get("customer_id") if isinstance(state, dict) else getattr(state, "customer_id", None)
    from_role = state.get("from_role", "merchant") if isinstance(state, dict) else getattr(state, "from_role", "merchant")
    turn_num = state.get("turn_number", 2) if isinstance(state, dict) else getattr(state, "turn_number", 2)
    now_iso = state.get("received_at", "") if isinstance(state, dict) else getattr(state, "received_at", "")

    return ReplyHandler.handle_reply(
        conversation_id=conv_id,
        merchant_id=mid,
        customer_id=cid,
        from_role=from_role,
        message=user_message,
        received_at=now_iso,
        turn_number=turn_num,
    )
