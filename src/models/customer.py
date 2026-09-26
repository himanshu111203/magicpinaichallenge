from __future__ import annotations

from typing import Any, Optional
from pydantic import BaseModel, ConfigDict, Field


class CustomerIdentity(BaseModel):
    """Demographic and contact information for a customer."""
    model_config = ConfigDict(extra="allow")

    name: str
    phone_redacted: Optional[str] = None
    language_pref: str
    age_band: str
    senior_citizen: Optional[bool] = None


class CustomerRelationship(BaseModel):
    """Historical patronage and transaction metrics."""
    model_config = ConfigDict(extra="allow")

    first_visit: Optional[str] = None
    last_visit: Optional[str] = None
    visits_total: Optional[int] = None
    services_received: list[str] = Field(default_factory=list)
    lifetime_value: Optional[float | int] = None
    favourite_dish: Optional[str] = None
    chronic_conditions: Optional[list[str]] = None


class CustomerPreferences(BaseModel):
    """
    Channel and scheduling preferences, plus loose vertical-specific attributes
    (e.g., preferred_slots, preferred_stylist, delivery_address, wedding_date).
    """
    model_config = ConfigDict(extra="allow")

    channel: Optional[str] = None
    reminder_opt_in: Optional[bool] = None
    preferred_slots: Optional[str | list[str]] = None
    preferred_stylist: Optional[str] = None
    delivery_address: Optional[str] = None
    wedding_date: Optional[str] = None
    training_focus: Optional[str] = None
    health_focus: Optional[str] = None
    family_size: Optional[int] = None
    household_size: Optional[int] = None
    office_nearby: Optional[bool] = None


class CustomerConsent(BaseModel):
    """Opt-in consent record and permitted channels/scopes."""
    model_config = ConfigDict(extra="allow")

    opted_in_at: Optional[str] = None
    scope: list[str] = Field(default_factory=list)


class CustomerContext(BaseModel):
    """
    Full contextual record for a patron associated with a merchant.
    Scope: customer.
    """
    model_config = ConfigDict(extra="allow")

    customer_id: str
    merchant_id: str
    state: str  # "new" | "active" | "lapsed_soft" | "lapsed_hard" | "churned"
    identity: CustomerIdentity
    relationship: CustomerRelationship
    preferences: CustomerPreferences
    consent: CustomerConsent

    @property
    def has_valid_consent(self) -> bool:
        """
        Returns True only if the customer has explicit opt-in timestamp,
        at least one granted consent scope, and a non-null phone number.
        """
        return bool(
            self.consent.opted_in_at
            and self.consent.scope
            and self.identity.phone_redacted
        )

    @property
    def is_anonymous_or_walkin(self) -> bool:
        """Returns True if the profile is an unconsented walk-in or placeholder."""
        return self.identity.phone_redacted is None or self.consent.opted_in_at is None
