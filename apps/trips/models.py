from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MinValueValidator, RegexValidator
from django.db import models
from django.urls import reverse

from apps.core.geo import CITY_CHOICES


class Vehicle(models.Model):
    class Type(models.TextChoices):
        VAN = "camionnette", "Camionnette"
        TRUCK = "camion", "Camion porteur"
        SEMI = "semi", "Semi-remorque"
        REEFER = "frigo", "Camion frigorifique"

    carrier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="vehicles")
    vehicle_type = models.CharField("type", max_length=20, choices=Type.choices)
    plate_number = models.CharField(
        "immatriculation",
        max_length=20,
        unique=True,
        validators=[RegexValidator(r"^[0-9A-Za-z \-]{4,20}$", "Immatriculation invalide.")],
    )
    capacity_kg = models.FloatField("charge utile (kg)", validators=[MinValueValidator(50)])
    capacity_m3 = models.FloatField("volume utile (m³)", validators=[MinValueValidator(0.5)])
    refrigerated = models.BooleanField("réfrigéré", default=False)

    class Meta:
        verbose_name = "véhicule"
        ordering = ["plate_number"]

    def __str__(self):
        return f"{self.get_vehicle_type_display()} {self.plate_number}"


class TripQuerySet(models.QuerySet):
    def visible(self):
        return self.filter(is_active=True)

    def open(self):
        return self.visible().filter(status=Trip.Status.OPEN)


class Trip(models.Model):
    """A carrier's planned route with free capacity."""

    class Status(models.TextChoices):
        OPEN = "ouvert", "Ouvert"
        FULL = "complet", "Complet"
        DONE = "termine", "Terminé"
        CANCELLED = "annule", "Annulé"

    class Pricing(models.TextChoices):
        PER_KG = "per_kg", "Prix au kg"
        FIXED = "fixed", "Prix forfaitaire"

    carrier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="trips")
    vehicle = models.ForeignKey(Vehicle, on_delete=models.PROTECT, related_name="trips", verbose_name="véhicule")
    origin = models.CharField("ville de départ", max_length=50, choices=CITY_CHOICES)
    destination = models.CharField("ville d'arrivée", max_length=50, choices=CITY_CHOICES)
    departure_date = models.DateField("date de départ")
    available_weight_kg = models.FloatField("poids disponible (kg)", validators=[MinValueValidator(1)])
    available_volume_m3 = models.FloatField("volume disponible (m³)", validators=[MinValueValidator(0.01)])
    reserved_weight_kg = models.FloatField(default=0)
    reserved_volume_m3 = models.FloatField(default=0)
    pricing_mode = models.CharField("mode de tarification", max_length=10, choices=Pricing.choices)
    price_per_kg = models.DecimalField(
        "prix au kg (TND)", max_digits=8, decimal_places=3, null=True, blank=True, validators=[MinValueValidator(0)]
    )
    fixed_price = models.DecimalField(
        "prix forfaitaire (TND)",
        max_digits=10,
        decimal_places=2,
        null=True,
        blank=True,
        validators=[MinValueValidator(0)],
    )
    notes = models.CharField("remarques", max_length=255, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN)
    is_active = models.BooleanField("visible", default=True)
    is_flagged = models.BooleanField("signalé par l'IA", default=False)
    fraud_score = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    objects = TripQuerySet.as_manager()

    class Meta:
        ordering = ["departure_date"]
        verbose_name = "trajet"
        indexes = [
            models.Index(fields=["origin", "destination"]),
            models.Index(fields=["departure_date"]),
            models.Index(fields=["status", "is_active"]),
        ]

    def __str__(self):
        return f"{self.origin} → {self.destination} le {self.departure_date:%d/%m/%Y}"

    def get_absolute_url(self):
        return reverse("trips:detail", args=[self.pk])

    @property
    def remaining_weight_kg(self) -> float:
        return max(self.available_weight_kg - self.reserved_weight_kg, 0)

    @property
    def remaining_volume_m3(self) -> float:
        return max(round(self.available_volume_m3 - self.reserved_volume_m3, 3), 0)

    def can_carry(self, weight_kg: float, volume_m3: float) -> bool:
        return weight_kg <= self.remaining_weight_kg and volume_m3 <= self.remaining_volume_m3

    def quote(self, weight_kg: float) -> Decimal | None:
        """Price the carrier would charge for ``weight_kg`` at its posted rate."""
        if self.pricing_mode == self.Pricing.FIXED:
            return self.fixed_price
        if self.price_per_kg is not None:
            return (self.price_per_kg * Decimal(str(weight_kg))).quantize(Decimal("0.01"))
        return None

    def clean(self):
        errors = {}
        if self.origin and self.origin == self.destination:
            errors["destination"] = "La destination doit être différente de la ville de départ."
        if self.pricing_mode == self.Pricing.PER_KG and self.price_per_kg is None:
            errors["price_per_kg"] = "Indiquez le prix au kg."
        if self.pricing_mode == self.Pricing.FIXED and self.fixed_price is None:
            errors["fixed_price"] = "Indiquez le prix forfaitaire."
        if self.vehicle_id and self.available_weight_kg:
            if self.available_weight_kg > self.vehicle.capacity_kg:
                errors["available_weight_kg"] = (
                    f"Dépasse la charge utile du véhicule ({self.vehicle.capacity_kg:g} kg)."
                )
            if self.available_volume_m3 and self.available_volume_m3 > self.vehicle.capacity_m3:
                errors["available_volume_m3"] = (
                    f"Dépasse le volume utile du véhicule ({self.vehicle.capacity_m3:g} m³)."
                )
        if errors:
            raise ValidationError(errors)
