"""AI job adapter for the price suggestion (see ``pricing.py`` for the model)."""

from datetime import date

from apps.core.ai.registry import AIInputError
from apps.core.choices import MerchandiseType
from apps.core.geo import canonical_city

from .pricing import suggest_price


def validate(payload: dict, user) -> dict:
    origin = canonical_city(str(payload.get("origin", "")))
    destination = canonical_city(str(payload.get("destination", "")))
    if not origin or not destination or origin == destination:
        raise AIInputError("Choisissez deux villes différentes.")
    try:
        weight = float(payload.get("weight_kg") or 0)
        volume = float(payload.get("volume_m3") or 0) or weight / 400
    except (TypeError, ValueError) as exc:
        raise AIInputError("Poids ou volume invalide.") from exc
    if weight <= 0:
        raise AIInputError("Indiquez un poids positif.")
    mtype = payload.get("merchandise_type") or MerchandiseType.AUTRE
    if mtype not in MerchandiseType.values:
        mtype = MerchandiseType.AUTRE
    urgency = 3
    try:
        if payload.get("pickup_date") and payload.get("delivery_deadline"):
            urgency = (
                date.fromisoformat(payload["delivery_deadline"]) - date.fromisoformat(payload["pickup_date"])
            ).days
    except ValueError:
        pass
    return {
        "origin": origin,
        "destination": destination,
        "weight_kg": weight,
        "volume_m3": round(volume, 3),
        "merchandise_type": mtype,
        "urgency_days": max(0, min(urgency, 10)),
    }


def handle(payload: dict, user) -> dict:
    result = suggest_price(**payload)
    result["provider"] = "local:sklearn-gbr"
    return result
