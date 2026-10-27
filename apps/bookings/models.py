from django.conf import settings
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse


class BookingRequest(models.Model):
    """A request pairing one annonce (FreightRequest) with one Trip.

    Sent either by the PME (from a trip) or by the transporteur (from an annonce).
    """

    class Status(models.TextChoices):
        PENDING = "en_attente", "En attente"
        ACCEPTED = "acceptee", "Acceptée"
        IN_PROGRESS = "en_cours", "En cours"
        DELIVERED = "livree", "Livrée"
        REFUSED = "refusee", "Refusée"
        CANCELLED = "annulee", "Annulée"

    ACTIVE_STATUSES = (Status.PENDING, Status.ACCEPTED, Status.IN_PROGRESS)

    freight = models.ForeignKey(
        "shipments.FreightRequest", on_delete=models.CASCADE, related_name="bookings", verbose_name="annonce"
    )
    trip = models.ForeignKey("trips.Trip", on_delete=models.CASCADE, related_name="bookings", verbose_name="trajet")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings_sent")
    receiver = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="bookings_received")
    message = models.TextField(max_length=1000, blank=True)
    proposed_price = models.DecimalField(
        "prix proposé (TND)", max_digits=10, decimal_places=2, validators=[MinValueValidator(1)]
    )
    status = models.CharField(max_length=12, choices=Status.choices, default=Status.PENDING, db_index=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "demande de réservation"
        verbose_name_plural = "demandes de réservation"
        indexes = [models.Index(fields=["sender", "status"]), models.Index(fields=["receiver", "status"])]

    def __str__(self):
        return f"Demande #{self.pk} — {self.freight.title} / {self.trip}"

    def get_absolute_url(self):
        return reverse("bookings:detail", args=[self.pk])

    @property
    def pme(self):
        return self.freight.pme

    @property
    def carrier(self):
        return self.trip.carrier

    def is_participant(self, user) -> bool:
        return user.pk in (self.sender_id, self.receiver_id)

    def other_party(self, user):
        return self.receiver if user.pk == self.sender_id else self.sender


class BookingStatusHistory(models.Model):
    booking = models.ForeignKey(BookingRequest, on_delete=models.CASCADE, related_name="history")
    from_status = models.CharField(max_length=12, choices=BookingRequest.Status.choices, blank=True)
    to_status = models.CharField(max_length=12, choices=BookingRequest.Status.choices)
    changed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    note = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["created_at", "pk"]
        verbose_name = "historique de statut"
        verbose_name_plural = "historiques de statut"

    def __str__(self):
        return f"#{self.booking_id}: {self.from_status or '∅'} → {self.to_status}"
