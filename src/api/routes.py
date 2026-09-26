from __future__ import annotations

import time
from typing import Any, Optional
from fastapi import APIRouter, Response, status
from pydantic import BaseModel, Field

from src.engine import decision_engine, suppression_engine
from src.services.context_store import context_store

router = APIRouter(prefix="/v1")
START_TIME = time.time()



class ContextIngestRequest(BaseModel):
    """Wire request for POST /v1/context."""
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    delivered_at: Optional[str] = None


class TickRequest(BaseModel):
    """Wire request for POST /v1/tick."""
    now: str
    available_triggers: list[str] = Field(default_factory=list)


class ReplyRequest(BaseModel):
    """Wire request for POST /v1/reply."""
    conversation_id: str
    merchant_id: Optional[str] = None
    customer_id: Optional[str] = None
    from_role: str = "merchant"
    message: str
    received_at: str
    turn_number: int


@router.get("/healthz")
async def healthz():
    """
    Health check endpoint polled every 60s by the judge harness.
    Returns server status, uptime in seconds, and loaded context counts.
    """
    uptime = int(time.time() - START_TIME)
    return {
        "status": "ok",
        "uptime_seconds": uptime,
        "contexts_loaded": context_store.counts(),
    }


@router.get("/metadata")
async def metadata():
    """
    Metadata describing the team, model approach, and version.
    """
    return {
        "team_name": "Vera Engine Team",
        "team_members": ["Antigravity", "Hemant Kumar Rohilla"],
        "model": "deterministic-hybrid-v1",
        "approach": "Deterministic semantic trigger-family routing with multi-tier fallback, grounded signal selection, and LLM wording polish.",
        "contact_email": "team@veraengine.local",
        "version": "1.0.0",
        "submitted_at": "2026-09-26T00:00:00Z",
    }


@router.post("/context")
async def ingest_context(req: ContextIngestRequest, response: Response):
    """
    Ingest a contextual entity (category, merchant, customer, trigger).
    Enforces strict idempotency, version ordering, payload size limit (500KB),
    and domain schema validation.
    """
    success, result_body, status_code = context_store.upsert(
        scope=req.scope,
        context_id=req.context_id,
        version=req.version,
        payload=req.payload,
        delivered_at=req.delivered_at,
    )
    response.status_code = status_code
    return result_body


@router.post("/tick")
async def tick(req: TickRequest):
    """
    Tick endpoint. Evaluates candidate triggers via Phase 4 DecisionEngine,
    enforcing per-merchant rate limits, suppression gates, and tick action caps.
    """
    suppression_engine.start_tick(now_iso=req.now)

    candidate_ids = req.available_triggers if req.available_triggers else None
    candidates = decision_engine.select_candidates(
        available_trigger_ids=candidate_ids,
        now_iso=req.now,
    )

    actions = []
    for cand in candidates:
        action = cand.to_tick_action()
        # Commit to suppression engine and conversation store
        suppression_engine.record_action(
            trigger=cand.trigger,
            conversation_id=action["conversation_id"],
            body=action["body"],
            now_iso=req.now,
            cta=action["cta"],
            rationale=action["rationale"],
        )
        actions.append(action)

    return {"actions": actions}



@router.post("/reply")
async def reply(req: ReplyRequest):
    """
    Reply endpoint handling inbound multi-turn responses.
    Implements immediate intent transition to action mode,
    WhatsApp Business auto-reply filtering, and hostile message handling.
    """
    from src.engine.reply_handler import ReplyHandler

    return ReplyHandler.handle_reply(
        conversation_id=req.conversation_id,
        merchant_id=req.merchant_id,
        customer_id=req.customer_id,
        from_role=req.from_role,
        message=req.message,
        received_at=req.received_at,
        turn_number=req.turn_number,
    )

class ChatRequest(BaseModel):
    """Wire request for POST /v1/chat."""
    category: str
    message: str
    conversation_id: Optional[str] = "conv_chat"
    turn: Optional[int] = 1


@router.post("/chat")
async def chat_endpoint(req: ChatRequest):
    """
    Chat endpoint for the minimal chatbot interface.
    Routes user message and active vertical category through ChatService,
    which invokes the real compose and decision engine.
    """
    from src.services.chat_service import ChatService

    return ChatService.process(
        category=req.category,
        message=req.message,
        conversation_id=req.conversation_id or "conv_chat",
        turn=req.turn or 1,
    )
