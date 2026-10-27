from django.conf import settings
from django.core.validators import MaxValueValidator, MinValueValidator
from django.db import models


class Review(models.Model):
    """Rating left by the PME on the carrier once a booking is delivered."""

    class Sentiment(models.TextChoices):
        POSITIVE = "positif", "Positif"
        NEUTRAL = "neutre", "Neutre"
        NEGATIVE = "negatif", "Négatif"

    booking = models.OneToOneField("bookings.BookingRequest", on_delete=models.CASCADE, related_name="review")
    author = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_written")
    carrier = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="reviews_received")
    rating = models.PositiveSmallIntegerField("note", validators=[MinValueValidator(1), MaxValueValidator(5)])
    comment = models.TextField("commentaire", max_length=1500)
    sentiment = models.CharField(max_length=10, choices=Sentiment.choices, blank=True)
    sentiment_confidence = models.FloatField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]
        indexes = [models.Index(fields=["carrier", "-created_at"])]
        verbose_name = "avis"
        verbose_name_plural = "avis"

    def __str__(self):
        return f"{self.rating}/5 pour {self.carrier} par {self.author}"
