"""AI job adapter for smart matching: annonce → best trips, or trip → best annonces."""

from datetime import timedelta

from django.core.exceptions import PermissionDenied
from django.urls import reverse

from apps.core.ai.registry import AIInputError
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

from . import matching

WINDOW_DAYS = 5


def validate(payload: dict, user) -> dict:
    try:
        if payload.get("freight_id"):
            freight = FreightRequest.objects.get(pk=int(payload["freight_id"]))
            if freight.pme_id != user.pk:
                raise PermissionDenied
            return {"freight_id": freight.pk}
        if payload.get("trip_id"):
            trip = Trip.objects.get(pk=int(payload["trip_id"]))
            if trip.carrier_id != user.pk:
                raise PermissionDenied
            return {"trip_id": trip.pk}
    except (FreightRequest.DoesNotExist, Trip.DoesNotExist, ValueError) as exc:
        raise AIInputError("Annonce ou trajet introuvable.") from exc
    raise AIInputError("Indiquez une annonce ou un trajet.")


def _reference_price(freight):
    if freight.budget:
        return None
    try:
        from apps.trips.pricing import suggest_price

        urgency = (freight.delivery_deadline - freight.pickup_date).days
        return suggest_price(
            freight.origin,
            freight.destination,
            freight.weight_kg,
            freight.volume_m3,
            freight.merchandise_type,
            max(0, min(urgency, 10)),
        )["price"]
    except Exception:
        return None


def handle(payload: dict, user) -> dict:
    if "freight_id" in payload:
        freight = FreightRequest.objects.get(pk=payload["freight_id"])
        candidates = (
            Trip.objects.open()
            .exclude(carrier=user)
            .filter(
                departure_date__gte=freight.pickup_date - timedelta(days=WINDOW_DAYS),
                departure_date__lte=freight.delivery_deadline + timedelta(days=WINDOW_DAYS),
            )
            .select_related("vehicle", "carrier", "carrier__carrier_profile")[:300]
        )
        by_id = {t.pk: t for t in candidates}
        ranked = matching.rank(
            matching.freight_features(freight),
            [matching.trip_features(t) for t in candidates],
            reference_price=_reference_price(freight),
        )
        results = []
        for feats, s in ranked:
            trip = by_id[feats.id]
            results.append(
                {
                    "id": trip.pk,
                    "label": f"{trip.origin} → {trip.destination} · {trip.departure_date:%d/%m}",
                    "subtitle": f"{trip.carrier.display_name} · {trip.remaining_weight_kg:g} kg dispo",
                    "url": reverse("trips:detail", args=[trip.pk]),
                    "action_url": reverse("bookings:create_from_trip", args=[trip.pk]) + f"?freight={freight.pk}",
                    **s,
                }
            )
        return {"direction": "freight_to_trips", "results": results, "provider": "local:weighted-score"}

    trip = Trip.objects.select_related("vehicle", "carrier", "carrier__carrier_profile").get(pk=payload["trip_id"])
    candidates = (
        FreightRequest.objects.open()
        .exclude(pme=user)
        .filter(
            pickup_date__lte=trip.departure_date + timedelta(days=WINDOW_DAYS),
            delivery_deadline__gte=trip.departure_date - timedelta(days=WINDOW_DAYS),
        )[:300]
    )
    by_id = {f.pk: f for f in candidates}
    ranked = matching.rank_freights(matching.trip_features(trip), [matching.freight_features(f) for f in candidates])
    results = []
    for feats, s in ranked:
        f = by_id[feats.id]
        results.append(
            {
                "id": f.pk,
                "label": f"{f.title}",
                "subtitle": f"{f.origin} → {f.destination} · {f.weight_kg:g} kg",
                "url": reverse("shipments:detail", args=[f.pk]),
                "action_url": reverse("bookings:create_from_freight", args=[f.pk]) + f"?trip={trip.pk}",
                **s,
            }
        )
    return {"direction": "trip_to_freights", "results": results, "provider": "local:weighted-score"}
