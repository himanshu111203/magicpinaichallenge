from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class TriggerPayload(BaseModel):
    """
    Trigger payload. Supports both seed payloads (with rich kind-specific data)
    and generated placeholder payloads (`{"placeholder": True, "metric_or_topic": kind}`).
    All additional fields are preserved and accessible via attributes or `.get()`.
    """
    model_config = ConfigDict(extra="allow")

    placeholder: Optional[bool] = False
    metric_or_topic: Optional[str] = None

    @property
    def is_placeholder(self) -> bool:
        return bool(self.placeholder)

    def get(self, key: str, default: Any = None) -> Any:
        """Helper to safely access fields whether defined as model attributes or extra fields."""
        if hasattr(self, key):
            val = getattr(self, key)
            if val is not None:
                return val
        if self.model_extra and key in self.model_extra:
            return self.model_extra[key]
        return default


class TriggerContext(BaseModel):
    """
    Complete trigger context received by the engine.
    Scope: trigger.
    """
    model_config = ConfigDict(extra="allow")

    id: str
    scope: str  # "merchant" | "customer"
    kind: str
    source: str  # "internal" | "external"
    merchant_id: str
    customer_id: Optional[str] = None
    payload: TriggerPayload
    urgency: int  # 1 to 5
    suppression_key: str
    expires_at: str

    @property
    def is_placeholder_payload(self) -> bool:
        return self.payload.is_placeholder
