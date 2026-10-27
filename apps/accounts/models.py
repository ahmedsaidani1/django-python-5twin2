from django.conf import settings
from django.contrib.auth.models import AbstractUser
from django.contrib.contenttypes.fields import GenericForeignKey
from django.contrib.contenttypes.models import ContentType
from django.core.validators import RegexValidator
from django.db import models
from django.urls import reverse

from apps.core.geo import CITY_CHOICES

phone_validator = RegexValidator(r"^\+?[0-9 ]{8,15}$", "Numéro de téléphone invalide (8 à 15 chiffres).")


class User(AbstractUser):
    class Role(models.TextChoices):
        PME = "pme", "PME / Expéditeur"
        TRANSPORTEUR = "transporteur", "Transporteur"
        ADMIN = "admin", "Administrateur"

    role = models.CharField(max_length=20, choices=Role.choices, default=Role.PME, db_index=True)
    phone = models.CharField("téléphone", max_length=20, blank=True, validators=[phone_validator])
    is_flagged = models.BooleanField("signalé par l'IA", default=False)
    fraud_score = models.FloatField(null=True, blank=True)

    class Meta:
        verbose_name = "utilisateur"

    @property
    def effective_role(self) -> str:
        return self.Role.ADMIN if (self.is_superuser or self.role == self.Role.ADMIN) else self.role

    @property
    def is_pme(self):
        return self.effective_role == self.Role.PME

    @property
    def is_transporteur(self):
        return self.effective_role == self.Role.TRANSPORTEUR

    @property
    def is_platform_admin(self):
        return self.effective_role == self.Role.ADMIN

    def get_absolute_url(self):
        if self.role == self.Role.TRANSPORTEUR:
            return reverse("accounts:carrier", args=[self.pk])
        return reverse("dashboard:home")

    @property
    def display_name(self):
        profile = getattr(self, "company_profile", None) or getattr(self, "carrier_profile", None)
        if profile and profile.company_name:
            return profile.company_name
        return self.get_full_name() or self.username


class CompanyProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="company_profile")
    company_name = models.CharField("raison sociale", max_length=150)
    sector = models.CharField("secteur", max_length=100, blank=True)
    city = models.CharField("ville", max_length=50, choices=CITY_CHOICES)
    address = models.CharField("adresse", max_length=255, blank=True)
    tax_id = models.CharField("matricule fiscal", max_length=30, blank=True)
    description = models.TextField(blank=True)

    class Meta:
        verbose_name = "profil PME"
        verbose_name_plural = "profils PME"

    def __str__(self):
        return self.company_name


class CarrierProfile(models.Model):
    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="carrier_profile")
    company_name = models.CharField("nom commercial", max_length=150)
    city = models.CharField("ville de base", max_length=50, choices=CITY_CHOICES)
    license_number = models.CharField("n° d'autorisation de transport", max_length=50, blank=True)
    description = models.TextField(blank=True)
    average_rating = models.FloatField("note moyenne", null=True, blank=True)
    reviews_count = models.PositiveIntegerField(default=0)
    reputation_score = models.FloatField("score de réputation (IA)", null=True, blank=True)

    class Meta:
        verbose_name = "profil transporteur"
        verbose_name_plural = "profils transporteur"

    def __str__(self):
        return self.company_name


class Report(models.Model):
    """A "signalement" of an annonce, a trip or a user, handled by an admin."""

    class Reason(models.TextChoices):
        SPAM = "spam", "Spam / publicité"
        FRAUD = "fraude", "Arnaque / fraude"
        INAPPROPRIATE = "inapproprie", "Contenu inapproprié"
        FAKE = "faux", "Informations fausses"
        OTHER = "autre", "Autre"

    class Status(models.TextChoices):
        OPEN = "ouvert", "Ouvert"
        RESOLVED = "traite", "Traité"
        REJECTED = "rejete", "Rejeté"

    reporter = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reports_made")
    content_type = models.ForeignKey(ContentType, on_delete=models.CASCADE)
    object_id = models.PositiveBigIntegerField()
    target = GenericForeignKey("content_type", "object_id")
    reason = models.CharField("motif", max_length=20, choices=Reason.choices)
    details = models.TextField("détails", max_length=1000, blank=True)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.OPEN, db_index=True)
    handled_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name="reports_handled"
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["content_type", "object_id"])]
        verbose_name = "signalement"

    def __str__(self):
        return f"Signalement {self.get_reason_display()} — {self.content_type.model} #{self.object_id}"
