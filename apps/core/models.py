from django.conf import settings
from django.db import models


class AIJob(models.Model):
    """One asynchronous AI call: what was asked, what came back, how long it took."""

    class Kind(models.TextChoices):
        SMART_ANNONCE = "smart_annonce", "Annonce intelligente"
        PRICE = "price", "Suggestion de prix"
        MATCHING = "matching", "Matching intelligent"
        SENTIMENT = "sentiment", "Analyse de sentiment"
        FRAUD = "fraud", "Détection de fraude"

    class Status(models.TextChoices):
        PENDING = "pending", "En attente"
        RUNNING = "running", "En cours"
        SUCCESS = "success", "Terminé"
        ERROR = "error", "Erreur"

    user = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, null=True, blank=True, related_name="ai_jobs"
    )
    kind = models.CharField(max_length=20, choices=Kind.choices)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.PENDING)
    input = models.JSONField(default=dict, blank=True)
    output = models.JSONField(default=dict, blank=True)
    error = models.TextField(blank=True)
    provider = models.CharField(max_length=40, blank=True)
    latency_ms = models.PositiveIntegerField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["kind", "status"]), models.Index(fields=["user", "-created_at"])]
        verbose_name = "tâche IA"
        verbose_name_plural = "tâches IA"

    def __str__(self):
        return f"{self.get_kind_display()} #{self.pk} ({self.status})"

    @property
    def is_finished(self):
        return self.status in (self.Status.SUCCESS, self.Status.ERROR)
