from __future__ import annotations

from enum import Enum


class TriggerFamily(str, Enum):
    """
    Semantic trigger families for routing and composing outreach.
    Per Ground Rule 18 and challenge_analysis.md §D, routing by semantic
    family ensures resilience against inconsistent or unseen kind strings.
    """
    RECALL_REMINDER = "recall_reminder"
    PERFORMANCE_MOVEMENT = "performance_movement"
    DORMANCY_LAPSE = "dormancy_lapse"
    RESEARCH_COMPLIANCE_TREND = "research_compliance_trend"
    MILESTONE = "milestone"
    PLANNING_INTENT = "planning_intent"
    SUPPLY_ALERT = "supply_alert"
    SEASONAL_EVENT = "seasonal_event"
    GENERAL_NUDGE = "general_nudge"


# Explicit exact-match table for known kinds (from seeds, generator, and brief)
EXACT_KIND_MAP: dict[str, TriggerFamily] = {
    # Recall / Reminders (Internal, often customer-scoped)
    "recall_due": TriggerFamily.RECALL_REMINDER,
    "appointment_tomorrow": TriggerFamily.RECALL_REMINDER,
    "chronic_refill_due": TriggerFamily.RECALL_REMINDER,
    "wedding_package_followup": TriggerFamily.RECALL_REMINDER,
    "trial_followup": TriggerFamily.RECALL_REMINDER,

    # Performance Movement (Internal merchant metrics)
    "perf_dip": TriggerFamily.PERFORMANCE_MOVEMENT,
    "perf_spike": TriggerFamily.PERFORMANCE_MOVEMENT,
    "seasonal_perf_dip": TriggerFamily.PERFORMANCE_MOVEMENT,

    # Dormancy & Lifecycle Lapse (Internal merchant/customer state)
    "dormant_with_vera": TriggerFamily.DORMANCY_LAPSE,
    "customer_lapsed_soft": TriggerFamily.DORMANCY_LAPSE,
    "customer_lapsed_hard": TriggerFamily.DORMANCY_LAPSE,
    "winback_eligible": TriggerFamily.DORMANCY_LAPSE,
    "winback": TriggerFamily.DORMANCY_LAPSE,
    "renewal_due": TriggerFamily.DORMANCY_LAPSE,

    # Research, Compliance & Category Trends (External industry signals)
    "research_digest": TriggerFamily.RESEARCH_COMPLIANCE_TREND,
    "regulation_change": TriggerFamily.RESEARCH_COMPLIANCE_TREND,
    "cde_opportunity": TriggerFamily.RESEARCH_COMPLIANCE_TREND,
    "category_trend_movement": TriggerFamily.RESEARCH_COMPLIANCE_TREND,

    # Milestones & Reviews (Internal merchant achievements/feedback)
    "milestone_reached": TriggerFamily.MILESTONE,
    "review_theme_emerged": TriggerFamily.MILESTONE,

    # Planning Intent & Program Drafting (Co-creation with merchant)
    "active_planning_intent": TriggerFamily.PLANNING_INTENT,
    "corporate_thali_planning": TriggerFamily.PLANNING_INTENT,
    "kids_yoga_program_drafting": TriggerFamily.PLANNING_INTENT,

    # Supply & Operational Alerts (External alerts / profile warnings)
    "supply_alert": TriggerFamily.SUPPLY_ALERT,
    "gbp_unverified": TriggerFamily.SUPPLY_ALERT,
    "competitor_opened": TriggerFamily.SUPPLY_ALERT,

    # Seasonal Events & Curiosity cadences (External calendar / scheduled rhythm)
    "festival_upcoming": TriggerFamily.SEASONAL_EVENT,
    "ipl_match_today": TriggerFamily.SEASONAL_EVENT,
    "category_seasonal": TriggerFamily.SEASONAL_EVENT,
    "curious_ask_due": TriggerFamily.SEASONAL_EVENT,
    "summer_demand_shift": TriggerFamily.SEASONAL_EVENT,
}


def classify_trigger_family(kind: str) -> TriggerFamily:
    """
    Deterministically maps a trigger kind string to its semantic TriggerFamily.
    Uses exact lookup first, followed by substring and semantic keyword matching.
    """
    if not kind:
        return TriggerFamily.GENERAL_NUDGE

    normalized = kind.strip().lower()

    # 1. Exact match check
    if normalized in EXACT_KIND_MAP:
        return EXACT_KIND_MAP[normalized]

    # 2. Substring & keyword heuristic matching for generated or unseen kinds
    # Recall / Reminders
    if any(k in normalized for k in ("recall", "appointment", "refill", "followup", "remind")):
        return TriggerFamily.RECALL_REMINDER

    # Performance Movement
    if any(k in normalized for k in ("perf", "metric", "views", "calls", "ctr", "delta")):
        return TriggerFamily.PERFORMANCE_MOVEMENT

    # Dormancy & Lapse
    if any(k in normalized for k in ("dormant", "lapse", "winback", "renew", "churn", "inactive")):
        return TriggerFamily.DORMANCY_LAPSE

    # Research & Compliance
    if any(k in normalized for k in ("research", "digest", "regulat", "compliance", "cde", "trend", "journal")):
        return TriggerFamily.RESEARCH_COMPLIANCE_TREND

    # Milestone & Reviews
    if any(k in normalized for k in ("milestone", "review", "rating", "achievement", "feedback")):
        return TriggerFamily.MILESTONE

    # Planning Intent
    if any(k in normalized for k in ("planning", "drafting", "program", "intent", "campaign_plan")):
        return TriggerFamily.PLANNING_INTENT

    # Supply & Competitor Alerts
    if any(k in normalized for k in ("supply", "alert", "competitor", "unverified", "gbp", "warning")):
        return TriggerFamily.SUPPLY_ALERT

    # Seasonal & Events
    if any(k in normalized for k in ("festival", "match", "seasonal", "summer", "winter", "event", "curious", "cadence")):
        return TriggerFamily.SEASONAL_EVENT

    return TriggerFamily.GENERAL_NUDGE
