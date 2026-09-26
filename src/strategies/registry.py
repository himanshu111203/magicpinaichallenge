from __future__ import annotations

from src.strategies.base import BaseStrategy
from src.strategies.dentists import DentistStrategy
from src.strategies.general import GeneralStrategy
from src.strategies.gyms import GymStrategy
from src.strategies.pharmacies import PharmacyStrategy
from src.strategies.restaurants import RestaurantStrategy
from src.strategies.salons import SalonStrategy

_STRATEGIES: dict[str, BaseStrategy] = {
    "dentists": DentistStrategy(),
    "salons": SalonStrategy(),
    "restaurants": RestaurantStrategy(),
    "gyms": GymStrategy(),
    "pharmacies": PharmacyStrategy(),
}
_GENERAL = GeneralStrategy()


def get_strategy(category_slug: str) -> BaseStrategy:
    """Return the vertical-specific composition strategy, or general fallback."""
    slug = category_slug.strip().lower() if category_slug else ""
    return _STRATEGIES.get(slug, _GENERAL)
