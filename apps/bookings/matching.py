"""AI #3 — Smart matching between annonces (freight) and trips.

A transparent weighted score in [0, 1] built from five sub-scores:
route (detour), date (window fit), capacity (fit + utilisation), price (vs budget or the
price model), and carrier rating. Hard constraints (capacity, refrigeration) zero the score.
Works on plain dataclasses so it can be evaluated offline on a labeled set.
"""

from dataclasses import dataclass, field
from datetime import date
from decimal import Decimal

from apps.core.geo import distance_km

WEIGHTS = {"route": 0.35, "date": 0.25, "capacity": 0.15, "price": 0.15, "rating": 0.10}
FRESH_TYPES = {"frais"}


@dataclass
class FreightFeatures:
    origin: str
    destination: str
    pickup_date: date
    delivery_deadline: date
    weight_kg: float
    volume_m3: float
    merchandise_type: str = "autre"
    constraints: str = ""
    budget: float | None = None
    id: int | None = None

    @property
    def needs_cold(self) -> bool:
        return self.merchandise_type in FRESH_TYPES or "frig" in self.constraints.lower()


@dataclass
class TripFeatures:
    origin: str
    destination: str
    departure_date: date
    remaining_weight_kg: float
    remaining_volume_m3: float
    refrigerated: bool = False
    price_per_kg: float | None = None
    fixed_price: float | None = None
    rating: float | None = None  # 1–5
    reputation: float | None = None  # 0–100 (AI reputation score)
    id: int | None = None
    extra: dict = field(default_factory=dict)

    def quote(self, weight_kg: float) -> float | None:
        if self.fixed_price is not None:
            return float(self.fixed_price)
        if self.price_per_kg is not None:
            return float(self.price_per_kg) * weight_kg
        return None


def route_score(f: FreightFeatures, t: TripFeatures) -> float:
    if f.origin == t.origin and f.destination == t.destination:
        return 1.0
    detour = distance_km(f.origin, t.origin) + distance_km(f.destination, t.destination)
    trip_len = distance_km(t.origin, t.destination) or 1
    return max(0.0, 1 - detour / (0.4 * trip_len + 40))


def date_score(f: FreightFeatures, t: TripFeatures) -> float:
    if f.pickup_date <= t.departure_date <= f.delivery_deadline:
        return 1.0
    gap = (
        (f.pickup_date - t.departure_date).days
        if t.departure_date < f.pickup_date
        else (t.departure_date - f.delivery_deadline).days
    )
    return max(0.0, 1 - gap / 4)


def capacity_score(f: FreightFeatures, t: TripFeatures) -> float:
    if f.weight_kg > t.remaining_weight_kg or f.volume_m3 > t.remaining_volume_m3:
        return 0.0
    utilisation = max(f.weight_kg / max(t.remaining_weight_kg, 1), f.volume_m3 / max(t.remaining_volume_m3, 0.01))
    return 0.6 + 0.4 * utilisation  # any fit is fine, a good load factor is better


def price_score(f: FreightFeatures, t: TripFeatures, reference: float | None) -> float:
    quote = t.quote(f.weight_kg)
    target = f.budget or reference
    if quote is None or not target:
        return 0.5
    ratio = quote / target
    return 1.0 if ratio <= 1 else max(0.0, 1 - (ratio - 1) * 2)


def rating_score(t: TripFeatures) -> float:
    if t.reputation is not None:
        return t.reputation / 100
    if t.rating is not None:
        return (t.rating - 1) / 4
    return 0.5


def score(f: FreightFeatures, t: TripFeatures, reference_price: float | None = None) -> dict:
    parts = {
        "route": route_score(f, t),
        "date": date_score(f, t),
        "capacity": capacity_score(f, t),
        "price": price_score(f, t, reference_price),
        "rating": rating_score(t),
    }
    total = sum(WEIGHTS[k] * v for k, v in parts.items())
    hard_fail = parts["capacity"] == 0 or (f.needs_cold and not t.refrigerated)
    if hard_fail:
        total *= 0.1
    return {"score": round(total, 4), "parts": {k: round(v, 3) for k, v in parts.items()}, "compatible": not hard_fail}


def rank(f: FreightFeatures, trips: list[TripFeatures], k: int = 5, reference_price=None):
    scored = [(t, score(f, t, reference_price)) for t in trips]
    scored.sort(key=lambda x: x[1]["score"], reverse=True)
    return scored[:k]


def rank_freights(t: TripFeatures, freights: list[FreightFeatures], k: int = 5):
    scored = [(f, score(f, t)) for f in freights]
    scored.sort(key=lambda x: x[1]["score"], reverse=True)
    return scored[:k]


# ---- ORM adapters -----------------------------------------------------------------


def _f(v):
    return float(v) if isinstance(v, Decimal) else v


def freight_features(obj) -> FreightFeatures:
    return FreightFeatures(
        id=obj.pk,
        origin=obj.origin,
        destination=obj.destination,
        pickup_date=obj.pickup_date,
        delivery_deadline=obj.delivery_deadline,
        weight_kg=obj.weight_kg,
        volume_m3=obj.volume_m3,
        merchandise_type=obj.merchandise_type,
        constraints=obj.constraints or "",
        budget=_f(obj.budget),
    )


def trip_features(obj) -> TripFeatures:
    profile = getattr(obj.carrier, "carrier_profile", None)
    return TripFeatures(
        id=obj.pk,
        origin=obj.origin,
        destination=obj.destination,
        departure_date=obj.departure_date,
        remaining_weight_kg=obj.remaining_weight_kg,
        remaining_volume_m3=obj.remaining_volume_m3,
        refrigerated=obj.vehicle.refrigerated,
        price_per_kg=_f(obj.price_per_kg) if obj.pricing_mode == "per_kg" else None,
        fixed_price=_f(obj.fixed_price) if obj.pricing_mode == "fixed" else None,
        rating=profile.average_rating if profile else None,
        reputation=profile.reputation_score if profile else None,
    )


# ---- Ranking metrics ----------------------------------------------------------------


def precision_at_k(ranked_relevances: list[int], k: int = 5, threshold: int = 2) -> float:
    top = ranked_relevances[:k]
    return sum(1 for r in top if r >= threshold) / k


def ndcg_at_k(ranked_relevances: list[int], k: int = 5) -> float:
    import math

    def dcg(rels):
        return sum((2**r - 1) / math.log2(i + 2) for i, r in enumerate(rels[:k]))

    ideal = dcg(sorted(ranked_relevances, reverse=True))
    return dcg(ranked_relevances) / ideal if ideal else 0.0
