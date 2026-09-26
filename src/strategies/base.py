from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Optional

from src.engine.semantic_family import TriggerFamily
from src.engine.signal_selector import CandidateSignalBundle
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)


class BaseStrategy(ABC):
    """Base interface for category-specific composition strategies."""

    @abstractmethod
    def compose_message(
        self,
        signals: CandidateSignalBundle,
        category: CategoryContext,
        merchant: MerchantContext,
        trigger: TriggerContext,
        customer: Optional[CustomerContext] = None,
    ) -> tuple[str, str, str]:
        """
        Returns a tuple of:
        (body: str, cta: str, rationale: str)
        """
        pass
