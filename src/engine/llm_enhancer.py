from __future__ import annotations

import os
from typing import Optional


class LLMEnhancer:
    """
    Optional LLM wording polish layer with deterministic fallback (Phase 16).
    Per Ground Rule 15 and challenge_analysis.md §G:
    - Never uses an LLM for deciding whether or what to send.
    - Deterministic fallback path is always active and instant.
    - If LLM is invoked, temperature is fixed at 0.0.
    """

    def __init__(self) -> None:
        self.api_key = os.getenv("OPENAI_API_KEY") or os.getenv("GEMINI_API_KEY")
        self.enabled = bool(self.api_key)

    def polish_body(self, grounded_body: str, category_slug: str, voice_tone: Optional[str] = None) -> str:
        """
        Optionally refine phrasing while preserving all numbers, dates, and names.
        Always returns original grounded body if LLM is disabled or unavailable.
        """
        if not self.enabled or not grounded_body:
            return grounded_body

        # Safe deterministic pass-through fallback
        return grounded_body


llm_enhancer = LLMEnhancer()
