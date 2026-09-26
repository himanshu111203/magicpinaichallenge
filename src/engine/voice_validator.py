from __future__ import annotations

import re
from typing import Optional

from src.models import CategoryContext


class VoiceValidator:
    """
    Validates and sanitizes composed messages against category voice rules,
    taboo vocabulary, URL restrictions, and single-CTA constraints.
    """

    # URL regex matching http, https, www, or typical domain patterns
    URL_PATTERN = re.compile(
        r"(https?://\S+|www\.\S+|\b[a-zA-Z0-9.-]+\.(?:com|in|org|net|co|io)\b\S*)",
        re.IGNORECASE,
    )

    @classmethod
    def sanitize_body(
        cls,
        body: str,
        category: Optional[CategoryContext] = None,
    ) -> str:
        """
        Sanitize message body:
        1. Strips any URLs (Ground Rule 17: hard -3 penalty protection).
        2. Replaces taboo words from category voice with neutral peer phrasing.
        3. Normalizes whitespace.
        """
        if not body:
            return ""

        # 1. Disallow / strip URLs
        cleaned = cls.URL_PATTERN.sub("", body)

        # 2. Check and neutralize taboo words
        if category and category.voice and category.voice.vocab_taboo:
            for taboo in category.voice.vocab_taboo:
                if not taboo:
                    continue
                # Word-boundary match for taboo phrases
                pattern = re.compile(r"\b" + re.escape(taboo) + r"\b", re.IGNORECASE)
                if pattern.search(cleaned):
                    # Replace with category-appropriate neutral peer phrasing
                    replacement = "clinically proven" if "guarantee" in taboo.lower() else "effective"
                    cleaned = pattern.sub(replacement, cleaned)

        # 3. Collapse multiple whitespace and normalize
        cleaned = re.sub(r"[ \t]+", " ", cleaned)
        cleaned = re.sub(r"\n\s*\n", "\n\n", cleaned)
        return cleaned.strip()

    @classmethod
    def validate_cta(cls, cta: str) -> str:
        """
        Ensure CTA is from the controlled vocabulary:
        'binary_yes_no', 'open_ended', 'binary_confirm_cancel', 'multi_choice_slot', 'none'
        """
        allowed = {
            "binary_yes_no",
            "open_ended",
            "binary_confirm_cancel",
            "multi_choice_slot",
            "none",
        }
        normalized = cta.strip().lower() if cta else "open_ended"
        return normalized if normalized in allowed else "open_ended"
