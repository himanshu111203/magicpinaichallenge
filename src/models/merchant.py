from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class MerchantIdentity(BaseModel):
    """Business identity, location, and owner attributes."""
    model_config = ConfigDict(extra="allow")

    name: str
    city: str
    locality: str
    place_id: str
    verified: bool
    languages: list[str] = Field(default_factory=list)
    owner_first_name: str
    established_year: int


class MerchantSubscription(BaseModel):
    """Subscription tier and validity tracking."""
    model_config = ConfigDict(extra="allow")

    status: str  # "active" | "trial" | "expired"
    plan: str    # "Trial" | "Basic" | "Pro"
    days_remaining: Optional[int] = None
    days_since_expiry: Optional[int] = None
    renewed_at: Optional[str] = None


class PerformanceDelta7d(BaseModel):
    """7-day metric deltas."""
    model_config = ConfigDict(extra="allow")

    views_pct: float | int
    calls_pct: float | int
    ctr_pct: Optional[float | int] = None


class MerchantPerformance(BaseModel):
    """30-day listing performance and weekly deltas."""
    model_config = ConfigDict(extra="allow")

    window_days: int = 30
    views: int
    calls: int
    directions: int
    ctr: float
    leads: int
    delta_7d: Optional[PerformanceDelta7d] = None


class MerchantOffer(BaseModel):
    """Promotional offer active on merchant profile."""
    model_config = ConfigDict(extra="allow")

    id: str
    title: str
    status: str
    started: Optional[str] = None
    ended: Optional[str] = None


class ConversationMessage(BaseModel):
    """A single turn in historical message exchanges with Vera."""
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    ts: str
    from_: str = Field(alias="from")
    body: str
    engagement: Optional[str] = None


class ReviewTheme(BaseModel):
    """Sentiment clusters extracted from merchant customer reviews."""
    model_config = ConfigDict(extra="allow")

    theme: str
    sentiment: str
    occurrences_30d: int
    common_quote: Optional[str] = None


class CustomerAggregate(BaseModel):
    """
    Aggregated customer portfolio metrics for the merchant.
    Common core: total_unique_ytd. Category-specific extras are preserved.
    """
    model_config = ConfigDict(extra="allow")

    total_unique_ytd: Optional[int] = None

    # Dentists
    retention_6mo_pct: Optional[float] = None
    high_risk_adult_count: Optional[int] = None
    lapsed_180d_plus: Optional[int] = None

    # Salons
    retention_3mo_pct: Optional[float] = None
    lapsed_90d_plus: Optional[int] = None

    # Restaurants
    dine_in_orders_30d: Optional[int] = None
    delivery_orders_30d: Optional[int] = None
    delivery_share_pct: Optional[float] = None
    repeat_customer_pct: Optional[float] = None

    # Gyms
    total_active_members: Optional[int] = None
    monthly_churn_pct: Optional[float] = None
    trial_to_paid_pct: Optional[float] = None

    # Pharmacies
    chronic_rx_count: Optional[int] = None


class MerchantContext(BaseModel):
    """
    Full context model for a merchant.
    Scope: merchant.
    """
    model_config = ConfigDict(extra="allow", populate_by_name=True)

    merchant_id: str
    category_slug: str
    identity: MerchantIdentity
    subscription: MerchantSubscription
    performance: MerchantPerformance
    offers: list[MerchantOffer] = Field(default_factory=list)
    conversation_history: list[ConversationMessage] = Field(default_factory=list)
    customer_aggregate: CustomerAggregate
    signals: list[str] = Field(default_factory=list)
    review_themes: list[ReviewTheme] = Field(default_factory=list)
