from django.conf import settings
from django.db import models


class Message(models.Model):
    """One message in the thread attached to a booking."""

    booking = models.ForeignKey("bookings.BookingRequest", on_delete=models.CASCADE, related_name="messages")
    sender = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="messages_sent")
    body = models.TextField("message", max_length=2000)
    created_at = models.DateTimeField(auto_now_add=True)
    read_at = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ["created_at", "pk"]
        indexes = [models.Index(fields=["booking", "created_at"])]

    def __str__(self):
        return f"{self.sender} — {self.body[:40]}"
