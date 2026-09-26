from __future__ import annotations

import warnings
from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field

warnings.filterwarnings("ignore", category=UserWarning, message='Field name "register" in "CategoryVoice" shadows an attribute')


class CategoryVoice(BaseModel):
    """Voice, tone, and vocabulary guidelines for a specific category."""
    model_config = ConfigDict(extra="allow", protected_namespaces=())

    tone: str
    register: str
    code_mix: str
    vocab_allowed: list[str] = Field(default_factory=list)
    vocab_taboo: list[str] = Field(default_factory=list)
    salutation_examples: list[str] = Field(default_factory=list)
    tone_examples: list[str] = Field(default_factory=list)


class OfferCatalogItem(BaseModel):
    """Pre-approved service and promotional offers available in the category."""
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    type: str
    value: str
    audience: str


class DigestItem(BaseModel):
    """Research briefs, regulatory updates, or professional insights."""
    model_config = ConfigDict(extra="allow")

    id: str
    kind: str
    title: str
    source: str
    summary: str
    actionable: str
    credits: Optional[int] = None
    trial_n: Optional[int] = None
    patient_segment: Optional[str] = None
    date: Optional[str] = None


class PatientContentItem(BaseModel):
    """Educational content and creative scripts tailored for customer distribution."""
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    channel: str
    length_seconds: int
    body: str


class SeasonalBeat(BaseModel):
    """Seasonal patterns, demand shifts, or operational beats."""
    model_config = ConfigDict(extra="allow")

    month_range: str
    note: str


class TrendSignal(BaseModel):
    """Search queries and YoY consumer interest deltas."""
    model_config = ConfigDict(extra="allow")

    query: str
    delta_yoy: float
    segment_age: str
    skew: str


class PeerStats(BaseModel):
    """
    Category benchmark statistics.
    Contains a core set of shared metrics across all verticals plus
    typed optional fields for category-specific metrics. Extra fields
    are preserved.
    """
    model_config = ConfigDict(extra="allow")

    scope: Optional[str] = "category"
    avg_rating: float
    avg_review_count: float | int
    avg_views_30d: float | int
    avg_calls_30d: float | int
    avg_directions_30d: float | int
    avg_ctr: float
    avg_photos: float | int
    avg_post_freq_days: float | int

    # Category-specific benchmarks
    retention_6mo_pct: Optional[float] = None
    retention_3mo_pct: Optional[float] = None
    retention_30d_pct: Optional[float] = None
    monthly_churn_pct: Optional[float] = None
    trial_to_paid_pct: Optional[float] = None
    delivery_share_pct: Optional[float] = None
    repeat_customer_pct: Optional[float] = None


class CategoryContext(BaseModel):
    """
    Complete contextual profile for a business vertical/category.
    Scope: category.
    """
    model_config = ConfigDict(extra="allow")

    slug: str
    display_name: str
    voice: CategoryVoice
    offer_catalog: list[OfferCatalogItem] = Field(default_factory=list)
    peer_stats: PeerStats
    digest: list[DigestItem] = Field(default_factory=list)
    patient_content_library: list[PatientContentItem] = Field(default_factory=list)
    seasonal_beats: list[SeasonalBeat] = Field(default_factory=list)
    trend_signals: list[TrendSignal] = Field(default_factory=list)
    regulatory_authorities: list[str] = Field(default_factory=list)
    professional_journals: list[str] = Field(default_factory=list)
