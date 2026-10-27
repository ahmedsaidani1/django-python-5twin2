from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator
from django.db import models
from django.urls import reverse

from apps.core.choices import MerchandiseType
from apps.core.geo import CITY_CHOICES


class FreightRequestQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_active=True)

    def open(self):
        return self.visible().filter(status=FreightRequest.Status.OPEN)


class FreightRequest(models.Model):
    """An "annonce": a PME's need to ship goods from A to B."""

    class Status(models.TextChoices):
        OPEN = "ouverte", "Ouverte"
        ASSIGNED = "attribuee", "Attribuée"
        CLOSED = "cloturee", "Clôturée"

    pme = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="freight_requests")
    title = models.CharField("titre", max_length=120)
    merchandise_type = models.CharField("type de marchandise", max_length=20, choices=MerchandiseType.choices)
    description = models.TextField(max_length=2000, blank=True)
    weight_kg = models.FloatField("poids (kg)", validators=[MinValueValidator(1)])
    volume_m3 = models.FloatField("volume (m³)", validators=[MinValueValidator(0.01)])
    origin = models.CharField("ville de départ", max_length=50, choices=CITY_CHOICES)
    destination = models.CharField("ville d'arrivée", max_length=50, choices=CITY_CHOICES)
    pickup_date = models.DateField("date d'enlèvement")
    delivery_deadline = models.DateField("date limite de livraison")
    constraints = models.CharField(
        "contraintes", max_length=255, blank=True, help_text="Ex. : fragile, réfrigéré, hayon"
    )
    budget = models.DecimalField(
        "budget (TND)", max_digits=10, decimal_places=2, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    is_active = models.BooleanField("visible", default=True)
    is_flagged = models.BooleanField("signalée par l'IA", default=False)
    fraud_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    objects = FreightRequestQuerySet.as_manager()

    class Meta:
        ordering = ["-created_at"]
        verbose_name = "annonce de fret"
        verbose_name_plural = "annonces de fret"
        indexes = [
            models.Index(fields=["origin", "destination"]),
            models.Index(fields=["pickup_date"]),
            models.Index(fields=["merchandise_type"]),
            models.Index(fields=["status", "is_active"]),
        ]

    def __str__(self):
        return f"{self.title} ({self.origin} → {self.destination})"

    def get_absolute_url(self):
        return reverse("shipments:detail", args=[self.pk])

    def clean(self):
        errors = {}
        if self.pickup_date and self.delivery_deadline and self.delivery_deadline < self.pickup_date:
            errors["delivery_deadline"] = "La date limite de livraison doit être postérieure à la date d'enlèvement."
        if self.origin and self.origin == self.destination:
            errors["destination"] = "La destination doit être différente de la ville de départ."
        if errors:
            raise ValidationError(errors)
