from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Optional

from src.engine.semantic_family import TriggerFamily, classify_trigger_family
from src.models import (
    CategoryContext,
    CustomerContext,
    MerchantContext,
    TriggerContext,
)


@dataclass
class GroundedFact:
    """A strictly grounded contextual fact with its source of truth."""
    field: str
    value: Any
    source: str
    citation: Optional[str] = None


@dataclass
class CandidateSignalBundle:
    """
    Extracted grounded signals for candidate ranking and composition.
    Strictly guarantees that all metrics, citations, and names originate
    from genuine ingested context — zero fabrication.
    """
    trigger_id: str
    merchant_id: str
    customer_id: Optional[str]
    category_slug: str
    semantic_family: TriggerFamily
    is_placeholder_payload: bool
    grounded_facts: list[GroundedFact] = field(default_factory=list)

    # Core merchant identity attributes (always present and grounded)
    merchant_name: str = ""
    owner_first_name: Optional[str] = None
    locality: str = ""
    city: str = ""

    # Specific grounded extracted signals
    primary_metric_name: Optional[str] = None
    primary_metric_value: Optional[Any] = None
    peer_benchmark_value: Optional[Any] = None
    active_offer_title: Optional[str] = None
    digest_item_title: Optional[str] = None
    digest_item_source: Optional[str] = None
    seasonal_beat_note: Optional[str] = None
    review_theme_name: Optional[str] = None
    review_theme_quote: Optional[str] = None
    stale_posts_days: Optional[int] = None

    # Customer specific signals (if customer-scoped)
    customer_name: Optional[str] = None
    customer_last_service: Optional[str] = None
    customer_last_visit: Optional[str] = None

    def get_fact(self, field_name: str) -> Optional[GroundedFact]:
        """Find the first fact matching field_name."""
        for f in self.grounded_facts:
            if f.field == field_name:
                return f
        return None

    @property
    def has_strong_signals(self) -> bool:
        """
        True if the candidate contains meaningful actionable data
        (e.g., active offer, performance delta, digest item, or customer history).
        """
        return bool(
            self.primary_metric_value is not None
            or self.active_offer_title is not None
            or self.digest_item_title is not None
            or self.customer_last_service is not None
            or self.review_theme_name is not None
        )


class SignalSelector:
    """
    Extracts grounded signals from trigger, merchant, category, and customer contexts.
    Handles both rich seed payloads and graceful fallback for placeholder payloads
    without hallucinating facts, numbers, or citations.
    """

    @classmethod
    def extract_signals(
        cls,
        trigger: TriggerContext,
        merchant: MerchantContext,
        category: CategoryContext,
        customer: Optional[CustomerContext] = None,
    ) -> CandidateSignalBundle:
        """Extract a structured signal bundle from the 4-context layers."""
        family = classify_trigger_family(trigger.kind)
        is_placeholder = trigger.is_placeholder_payload
        facts: list[GroundedFact] = []

        # 1. Base Grounded Merchant Identity
        m_name = merchant.identity.name
        m_owner = merchant.identity.owner_first_name
        m_locality = merchant.identity.locality
        m_city = merchant.identity.city

        facts.append(GroundedFact("merchant_name", m_name, "merchant.identity.name"))
        facts.append(GroundedFact("owner_first_name", m_owner, "merchant.identity.owner_first_name"))
        facts.append(GroundedFact("locality", m_locality, "merchant.identity.locality"))
        facts.append(GroundedFact("city", m_city, "merchant.identity.city"))

        primary_metric_name: Optional[str] = None
        primary_metric_val: Optional[Any] = None
        peer_benchmark_val: Optional[Any] = None
        active_offer_title: Optional[str] = None
        digest_title: Optional[str] = None
        digest_source: Optional[str] = None
        seasonal_note: Optional[str] = None
        review_name: Optional[str] = None
        review_quote: Optional[str] = None
        cust_name: Optional[str] = None
        cust_last_srv: Optional[str] = None
        cust_last_vis: Optional[str] = None

        # 2. Active Offer Extraction (Real merchant offer catalog)
        active_offers = [o for o in merchant.offers if o.status == "active"]
        if active_offers:
            active_offer_title = active_offers[0].title
            facts.append(GroundedFact(
                "active_offer",
                active_offer_title,
                "merchant.offers",
                citation=active_offers[0].id,
            ))

        # 3. Customer History Extraction (if applicable)
        if customer:
            cust_name = customer.identity.name
            cust_last_vis = customer.relationship.last_visit
            if customer.relationship.services_received:
                cust_last_srv = customer.relationship.services_received[-1]

            facts.append(GroundedFact("customer_name", cust_name, "customer.identity.name"))

        # Extract merchant signals (e.g. stale_posts:22d)
        stale_posts_days: Optional[int] = None
        for s in merchant.signals:
            if isinstance(s, str) and s.startswith("stale_posts:"):
                try:
                    stale_posts_days = int(s.split(":")[1].replace("d", ""))
                    facts.append(GroundedFact("stale_posts_days", stale_posts_days, "merchant.signals"))
                except (IndexError, ValueError):
                    pass
            if cust_last_vis:
                facts.append(GroundedFact("customer_last_visit", cust_last_vis, "customer.relationship.last_visit"))
            if cust_last_srv:
                facts.append(GroundedFact("customer_last_service", cust_last_srv, "customer.relationship.services_received"))

        # 4. Payload-Specific vs. Placeholder Fallback Extraction
        if not is_placeholder:
            # Rich seed payload extraction
            payload = trigger.payload

            # Research digest items
            if payload.get("top_item"):
                item = payload.get("top_item")
                if isinstance(item, dict):
                    digest_title = item.get("title")
                    digest_source = item.get("source")
                    facts.append(GroundedFact(
                        "research_digest_title",
                        digest_title,
                        "trigger.payload.top_item.title",
                        citation=digest_source,
                    ))
                    if item.get("trial_n"):
                        facts.append(GroundedFact("trial_n", item.get("trial_n"), "trigger.payload.top_item.trial_n"))
                    if item.get("patient_segment"):
                        facts.append(GroundedFact("patient_segment", item.get("patient_segment"), "trigger.payload.top_item.patient_segment"))
            elif payload.get("top_item_id"):
                top_id = payload.get("top_item_id")
                match_digest = next((d for d in category.digest if d.id == top_id), None)
                if match_digest:
                    digest_title = match_digest.title
                    digest_source = match_digest.source
                    facts.append(GroundedFact(
                        "research_digest_title",
                        digest_title,
                        f"category.digest[{match_digest.id}].title",
                        citation=digest_source,
                    ))
                    if match_digest.trial_n:
                        facts.append(GroundedFact("trial_n", match_digest.trial_n, f"category.digest[{match_digest.id}].trial_n"))
                    if match_digest.patient_segment:
                        facts.append(GroundedFact("patient_segment", match_digest.patient_segment, f"category.digest[{match_digest.id}].patient_segment"))


            # Specific performance metrics
            if payload.get("delta_pct") is not None:
                primary_metric_val = payload.get("delta_pct")
                primary_metric_name = payload.get("metric", "performance_delta")
                facts.append(GroundedFact(
                    primary_metric_name,
                    primary_metric_val,
                    "trigger.payload.delta_pct",
                ))

            # Seasonal / Event / Festival payload
            if payload.get("event_name"):
                seasonal_note = f"{payload.get('event_name')} in {payload.get('days_until', '?')} days"
                facts.append(GroundedFact("event_name", payload.get("event_name"), "trigger.payload.event_name"))
            elif payload.get("festival"):
                seasonal_note = f"{payload.get('festival')} upcoming"
                facts.append(GroundedFact("festival", payload.get("festival"), "trigger.payload.festival"))

            # Milestone payload
            if payload.get("milestone"):
                primary_metric_name = "milestone"
                primary_metric_val = payload.get("milestone")
                facts.append(GroundedFact("milestone", primary_metric_val, "trigger.payload.milestone"))

        else:
            # Placeholder payload: Gracefully ground against merchant/category/customer state
            topic = (trigger.payload.metric_or_topic or "").lower()

            # A. Performance fallbacks
            if family == TriggerFamily.PERFORMANCE_MOVEMENT or "call" in topic or "view" in topic:
                if merchant.performance.delta_7d:
                    if "call" in topic or merchant.performance.delta_7d.calls_pct != 0:
                        primary_metric_name = "calls_delta_7d"
                        primary_metric_val = merchant.performance.delta_7d.calls_pct
                    else:
                        primary_metric_name = "views_delta_7d"
                        primary_metric_val = merchant.performance.delta_7d.views_pct
                    facts.append(GroundedFact(
                        primary_metric_name,
                        primary_metric_val,
                        f"merchant.performance.delta_7d.{primary_metric_name}",
                    ))
                else:
                    primary_metric_name = "views_30d"
                    primary_metric_val = merchant.performance.views
                    facts.append(GroundedFact("views_30d", primary_metric_val, "merchant.performance.views"))

                # Reference category peer benchmark for context
                if hasattr(category.peer_stats, "avg_calls_30d") and "call" in (primary_metric_name or ""):
                    peer_benchmark_val = category.peer_stats.avg_calls_30d
                    facts.append(GroundedFact("peer_avg_calls_30d", peer_benchmark_val, "category.peer_stats.avg_calls_30d"))

            # B. Research & trend fallbacks (use real category digest or trend items)
            elif family == TriggerFamily.RESEARCH_COMPLIANCE_TREND or "research" in topic or "trend" in topic:
                if category.digest:
                    top_digest = category.digest[0]
                    digest_title = top_digest.title
                    digest_source = top_digest.source
                    facts.append(GroundedFact(
                        "category_digest_title",
                        digest_title,
                        "category.digest[0].title",
                        citation=digest_source,
                    ))
                elif category.trend_signals:
                    top_trend = category.trend_signals[0]
                    digest_title = f"{top_trend.query} (+{int(top_trend.delta_yoy * 100)}% YoY)"
                    facts.append(GroundedFact("trend_query", top_trend.query, "category.trend_signals[0].query"))

            # C. Seasonal beats fallback
            elif family == TriggerFamily.SEASONAL_EVENT or "seasonal" in topic:
                if category.seasonal_beats:
                    beat = category.seasonal_beats[0]
                    seasonal_note = f"{beat.month_range}: {beat.note}"
                    facts.append(GroundedFact("seasonal_beat", seasonal_note, "category.seasonal_beats[0]"))

            # D. Review theme fallback
            if merchant.review_themes:
                top_review = merchant.review_themes[0]
                review_name = top_review.theme
                review_quote = top_review.common_quote
                facts.append(GroundedFact("review_theme", review_name, "merchant.review_themes[0].theme"))
                if review_quote:
                    facts.append(GroundedFact("review_quote", review_quote, "merchant.review_themes[0].common_quote"))

        return CandidateSignalBundle(
            trigger_id=trigger.id,
            merchant_id=merchant.merchant_id,
            customer_id=customer.customer_id if customer else None,
            category_slug=category.slug,
            semantic_family=family,
            is_placeholder_payload=is_placeholder,
            grounded_facts=facts,
            merchant_name=m_name,
            owner_first_name=m_owner,
            locality=m_locality,
            city=m_city,
            primary_metric_name=primary_metric_name,
            primary_metric_value=primary_metric_val,
            peer_benchmark_value=peer_benchmark_val,
            active_offer_title=active_offer_title,
            digest_item_title=digest_title,
            digest_item_source=digest_source,
            seasonal_beat_note=seasonal_note,
            review_theme_name=review_name,
            review_theme_quote=review_quote,
            customer_name=cust_name,
            customer_last_service=cust_last_srv,
            customer_last_visit=cust_last_vis,
            stale_posts_days=stale_posts_days,
        )
