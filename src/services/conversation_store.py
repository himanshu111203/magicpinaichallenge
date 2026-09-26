from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import re
import threading
from typing import Optional


def normalize_text(text: str) -> str:
    """Normalize text for verbatim comparison (lowercased, stripped, collapsed whitespace)."""
    text = text.strip().lower()
    return re.sub(r"\s+", " ", text)


@dataclass
class TurnRecord:
    """A single turn in a conversation."""
    from_role: str  # "vera" | "merchant" | "customer"
    body: str
    ts: str
    turn_number: int
    cta: Optional[str] = None
    rationale: Optional[str] = None


@dataclass
class ConversationRecord:
    """Complete record of a multi-turn conversation."""
    conversation_id: str
    merchant_id: str
    customer_id: Optional[str] = None
    trigger_id: Optional[str] = None
    suppression_key: Optional[str] = None
    status: str = "active"  # "active" | "waiting" | "ended"
    created_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    last_turn_at: str = field(default_factory=lambda: datetime.now(timezone.utc).isoformat())
    turns: list[TurnRecord] = field(default_factory=list)
    sent_bodies_normalized: set[str] = field(default_factory=set)

    def add_turn(self, turn: TurnRecord) -> None:
        self.turns.append(turn)
        self.last_turn_at = turn.ts
        if turn.from_role == "vera":
            self.sent_bodies_normalized.add(normalize_text(turn.body))

    def has_sent_body(self, body: str) -> bool:
        """Checks if Vera has already sent this exact verbatim body in this conversation."""
        return normalize_text(body) in self.sent_bodies_normalized


class ConversationStore:
    """
    Thread-safe in-memory store for active and historical conversations.
    Enforces turn tracking, verbatim repetition detection, and lifecycle status.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._conversations: dict[str, ConversationRecord] = {}

    def create_conversation(
        self,
        conversation_id: str,
        merchant_id: str,
        customer_id: Optional[str] = None,
        trigger_id: Optional[str] = None,
        suppression_key: Optional[str] = None,
        initial_turn: Optional[TurnRecord] = None,
    ) -> ConversationRecord:
        """Create and track a new conversation."""
        with self._lock:
            record = ConversationRecord(
                conversation_id=conversation_id,
                merchant_id=merchant_id,
                customer_id=customer_id,
                trigger_id=trigger_id,
                suppression_key=suppression_key,
            )
            if initial_turn:
                record.add_turn(initial_turn)
            self._conversations[conversation_id] = record
            return record

    def get(self, conversation_id: str) -> Optional[ConversationRecord]:
        """Retrieve conversation by ID."""
        with self._lock:
            return self._conversations.get(conversation_id)

    def add_turn(self, conversation_id: str, turn: TurnRecord) -> bool:
        """Append a turn to an existing conversation."""
        with self._lock:
            record = self._conversations.get(conversation_id)
            if not record:
                return False
            record.add_turn(turn)
            return True

    def has_sent_body(self, conversation_id: str, body: str) -> bool:
        """Check if body was previously sent by Vera in this conversation."""
        with self._lock:
            record = self._conversations.get(conversation_id)
            if not record:
                return False
            return record.has_sent_body(body)

    def get_by_merchant(self, merchant_id: str) -> list[ConversationRecord]:
        """Retrieve all conversations for a merchant."""
        with self._lock:
            return [c for c in self._conversations.values() if c.merchant_id == merchant_id]

    def end_conversation(self, conversation_id: str) -> bool:
        """Mark a conversation as ended."""
        with self._lock:
            record = self._conversations.get(conversation_id)
            if record:
                record.status = "ended"
                return True
            return False

    def count(self) -> int:
        """Total number of tracked conversations."""
        with self._lock:
            return len(self._conversations)

    def clear(self) -> None:
        """Reset conversation store."""
        with self._lock:
            self._conversations.clear()


# Global singleton instance
conversation_store = ConversationStore()
