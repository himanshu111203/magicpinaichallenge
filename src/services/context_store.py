from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime, timezone
import threading
from typing import Any, Optional

from pydantic import ValidationError

from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)

VALID_SCOPES = frozenset({"category", "merchant", "customer", "trigger"})
MAX_PAYLOAD_BYTES = 500 * 1024  # 500 KB limit per competition spec


@dataclass
class ContextRecord:
    """An in-memory record of an ingested context."""
    scope: str
    context_id: str
    version: int
    payload: dict[str, Any]
    model: Any
    stored_at: str
    delivered_at: Optional[str] = None


class ContextStore:
    """
    Thread-safe, in-memory repository for challenge contexts.
    Keyed on (scope, context_id).
    Enforces strict versioning, idempotency, size checks, and Pydantic validation.
    """

    def __init__(self) -> None:
        self._lock = threading.RLock()
        self._store: dict[tuple[str, str], ContextRecord] = {}
        self._counts: dict[str, int] = {
            "category": 0,
            "merchant": 0,
            "customer": 0,
            "trigger": 0,
        }

    def upsert(
        self,
        scope: str,
        context_id: str,
        version: int,
        payload: dict[str, Any],
        delivered_at: Optional[str] = None,
    ) -> tuple[bool, dict[str, Any], int]:
        """
        Upsert a context record.
        Returns: (success: bool, response_dict: dict, http_status_code: int)
        """
        with self._lock:
            # 1. Scope validation
            if scope not in VALID_SCOPES:
                return False, {
                    "accepted": False,
                    "reason": "invalid_scope",
                    "details": f"Unknown scope '{scope}'. Must be one of {sorted(VALID_SCOPES)}",
                }, 400

            # 2. Payload size validation (500 KB cap)
            try:
                payload_bytes = len(json.dumps(payload).encode("utf-8"))
            except (TypeError, ValueError) as e:
                return False, {
                    "accepted": False,
                    "reason": "invalid_payload",
                    "details": f"Payload serialization failed: {e}",
                }, 400

            if payload_bytes > MAX_PAYLOAD_BYTES:
                return False, {
                    "accepted": False,
                    "reason": "payload_too_large",
                    "details": f"Payload size {payload_bytes} bytes exceeds 500KB cap ({MAX_PAYLOAD_BYTES} bytes)",
                }, 413

            # 3. Version comparison if key exists
            key = (scope, context_id)
            if key in self._store:
                cur_record = self._store[key]
                if cur_record.version > version:
                    return False, {
                        "accepted": False,
                        "reason": "stale_version",
                        "current_version": cur_record.version,
                    }, 409

            # 4. Pydantic schema validation
            try:
                parsed_model = self._validate_payload(scope, payload)
            except ValidationError as e:
                return False, {
                    "accepted": False,
                    "reason": "invalid_payload",
                    "details": f"Schema validation error for scope '{scope}': {e.errors()[:3]}",
                }, 400
            except Exception as e:
                return False, {
                    "accepted": False,
                    "reason": "invalid_payload",
                    "details": str(e),
                }, 400

            # 5. Atomic store
            now_iso = datetime.now(timezone.utc).isoformat()
            is_new = key not in self._store

            record = ContextRecord(
                scope=scope,
                context_id=context_id,
                version=version,
                payload=payload,
                model=parsed_model,
                stored_at=now_iso,
                delivered_at=delivered_at,
            )
            self._store[key] = record

            if is_new:
                self._counts[scope] += 1

            if scope == "category":
                from src.engine import suppression_engine
                suppression_engine.reset()

            ack_id = f"ack_{context_id}_v{version}"
            return True, {
                "accepted": True,
                "ack_id": ack_id,
                "stored_at": now_iso,
            }, 200

    def _validate_payload(self, scope: str, payload: dict[str, Any]) -> Any:
        """Validate payload against the scope's domain model."""
        if scope == "category":
            return CategoryContext.model_validate(payload)
        elif scope == "merchant":
            return MerchantContext.model_validate(payload)
        elif scope == "customer":
            return CustomerContext.model_validate(payload)
        elif scope == "trigger":
            return TriggerContext.model_validate(payload)
        raise ValueError(f"Unrecognized scope: {scope}")

    def get(self, scope: str, context_id: str) -> Optional[ContextRecord]:
        """Retrieve a raw ContextRecord if present."""
        with self._lock:
            return self._store.get((scope, context_id))

    def get_model(self, scope: str, context_id: str) -> Optional[Any]:
        """Retrieve the validated Pydantic model for a context."""
        with self._lock:
            record = self._store.get((scope, context_id))
            return record.model if record else None

    def get_payload(self, scope: str, context_id: str) -> Optional[dict[str, Any]]:
        """Retrieve the raw payload dict for a context."""
        with self._lock:
            record = self._store.get((scope, context_id))
            return record.payload if record else None

    def get_by_scope(self, scope: str) -> list[ContextRecord]:
        """Retrieve all records for a scope."""
        with self._lock:
            return [rec for (s, _), rec in self._store.items() if s == scope]

    def get_models_by_scope(self, scope: str) -> list[Any]:
        """Retrieve all validated models for a scope."""
        with self._lock:
            return [rec.model for (s, _), rec in self._store.items() if s == scope]

    def counts(self) -> dict[str, int]:
        """Return the current counts of loaded contexts across all scopes."""
        with self._lock:
            return dict(self._counts)

    def total_count(self) -> int:
        """Total number of loaded contexts."""
        with self._lock:
            return len(self._store)

    def clear(self) -> None:
        """Reset the store to a completely empty state."""
        with self._lock:
            self._store.clear()
            self._counts = {
                "category": 0,
                "merchant": 0,
                "customer": 0,
                "trigger": 0,
            }


# Global singleton instance for the server application
context_store = ContextStore()
