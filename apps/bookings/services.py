"""Booking status machine.

    en_attente ──accept──▶ acceptee ──start──▶ en_cours ──deliver──▶ livree
        │  └──refuse──▶ refusee         │
        └──cancel──▶ annulee ◀──cancel──┘

Who may trigger each transition:
- accept / refuse: the receiver of the request;
- cancel from en_attente: the sender; cancel from acceptee: either party;
- start / deliver: the carrier (owner of the trip).
"""

from django.db import transaction
from django.urls import reverse

from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

from .models import BookingRequest, BookingStatusHistory

S = BookingRequest.Status

# Each transition is authorized only for a specific actor of the booking workflow.
SENDER, RECEIVER, CARRIER, PARTICIPANT = "sender", "receiver", "carrier", "participant"

# A transition is valid only when the current status and target status are paired
# with the correct role-based actor permitted to trigger it.
TRANSITIONS: dict[tuple[str, str], str] = {
    (S.PENDING, S.ACCEPTED): RECEIVER,
    (S.PENDING, S.REFUSED): RECEIVER,
    (S.PENDING, S.CANCELLED): SENDER,
    (S.ACCEPTED, S.IN_PROGRESS): CARRIER,
    (S.ACCEPTED, S.CANCELLED): PARTICIPANT,
    (S.IN_PROGRESS, S.DELIVERED): CARRIER,
}

ACTION_TARGETS = {
    "accepter": S.ACCEPTED,
    "refuser": S.REFUSED,
    "annuler": S.CANCELLED,
    "demarrer": S.IN_PROGRESS,
    "livrer": S.DELIVERED,
}

ACTION_LABELS = {
    "accepter": "Accepter",
    "refuser": "Refuser",
    "annuler": "Annuler",
    "demarrer": "Démarrer la livraison",
    "livrer": "Marquer comme livrée",
}


class InvalidTransition(Exception):
    """Transition not allowed from the current status, or not by this user."""


def _actor_matches(booking: BookingRequest, user, actor: str) -> bool:
    if actor == SENDER:
        return user.pk == booking.sender_id
    if actor == RECEIVER:
        return user.pk == booking.receiver_id
    if actor == CARRIER:
        return user.pk == booking.trip.carrier_id
    return booking.is_participant(user)


def can_transition(booking: BookingRequest, to_status: str, user) -> bool:
    actor = TRANSITIONS.get((booking.status, to_status))
    return actor is not None and _actor_matches(booking, user, actor)


def available_actions(booking: BookingRequest, user) -> list[tuple[str, str]]:
    return [(a, ACTION_LABELS[a]) for a, target in ACTION_TARGETS.items() if can_transition(booking, target, user)]


def record_history(booking, from_status, to_status, user=None, note=""):
    return BookingStatusHistory.objects.create(
        booking=booking, from_status=from_status, to_status=to_status, changed_by=user, note=note
    )


def create_booking(*, freight: FreightRequest, trip: Trip, sender, message: str, proposed_price) -> BookingRequest:
    # A booking is always created between the sender and the other party involved in the deal.
    # The receiver is the trip carrier when the sender is the freight owner, or the freight owner otherwise.
    receiver = trip.carrier if sender.pk == freight.pme_id else freight.pme
    with transaction.atomic():
        booking = BookingRequest.objects.create(
            freight=freight,
            trip=trip,
            sender=sender,
            receiver=receiver,
            message=message,
            proposed_price=proposed_price,
        )
        record_history(booking, "", S.PENDING, sender, "Demande créée")
    notify(
        receiver,
        Notification.Kind.NEW_REQUEST,
        f"Nouvelle demande de {sender.display_name} pour « {freight.title} »",
        booking.get_absolute_url(),
    )
    return booking


def transition(booking: BookingRequest, to_status: str, user, note: str = "") -> BookingRequest:
    """Apply a transition atomically, keep capacity/annonce states consistent, notify."""
    with transaction.atomic():
        booking = BookingRequest.objects.select_for_update().select_related("trip", "freight").get(pk=booking.pk)
        if not can_transition(booking, to_status, user):
            raise InvalidTransition(
                f"Transition « {booking.get_status_display()} → {S(to_status).label} » non autorisée."
            )
        trip = Trip.objects.select_for_update().get(pk=booking.trip_id)
        freight = booking.freight
        from_status = booking.status

        # Accepting a booking consumes the trip's remaining capacity and marks the demand
        # as assigned to this trip, preventing other pending offers from competing for the same freight.
        if to_status == S.ACCEPTED:
            if not trip.can_carry(freight.weight_kg, freight.volume_m3):
                raise InvalidTransition("Capacité restante du trajet insuffisante pour cette annonce.")
            if freight.status != FreightRequest.Status.OPEN:
                raise InvalidTransition("Cette annonce est déjà attribuée.")
            trip.reserved_weight_kg += freight.weight_kg
            trip.reserved_volume_m3 += freight.volume_m3
            if trip.remaining_weight_kg <= 0 or trip.remaining_volume_m3 <= 0:
                trip.status = Trip.Status.FULL
            freight.status = FreightRequest.Status.ASSIGNED
        elif to_status == S.CANCELLED and from_status == S.ACCEPTED:
            trip.reserved_weight_kg = max(trip.reserved_weight_kg - freight.weight_kg, 0)
            trip.reserved_volume_m3 = max(trip.reserved_volume_m3 - freight.volume_m3, 0)
            if trip.status == Trip.Status.FULL:
                trip.status = Trip.Status.OPEN
            freight.status = FreightRequest.Status.OPEN
        elif to_status == S.DELIVERED:
            freight.status = FreightRequest.Status.CLOSED

        trip.save(update_fields=["reserved_weight_kg", "reserved_volume_m3", "status"])
        freight.save(update_fields=["status"])
        booking.status = to_status
        booking.save(update_fields=["status", "updated_at"])
        record_history(booking, from_status, to_status, user, note)

        auto_refused = []
        # Once one request is accepted, every other pending request for the same freight
        # is automatically rejected to maintain a single successful assignment.
        if to_status == S.ACCEPTED:
            for other in BookingRequest.objects.filter(freight=freight, status=S.PENDING).exclude(pk=booking.pk):
                other.status = S.REFUSED
                other.save(update_fields=["status", "updated_at"])
                record_history(other, S.PENDING, S.REFUSED, None, "Annonce attribuée à une autre offre")
                auto_refused.append(other)

    label = S(to_status).label.lower()
    notify(
        booking.other_party(user),
        Notification.Kind.STATUS,
        f"Demande #{booking.pk} « {freight.title} » : {label} par {user.display_name}",
        booking.get_absolute_url(),
    )
    for other in auto_refused:
        notify(
            other.sender,
            Notification.Kind.STATUS,
            f"Votre demande #{other.pk} a été refusée : annonce attribuée à une autre offre",
            reverse("bookings:detail", args=[other.pk]),
        )
    return booking
