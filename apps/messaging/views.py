from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Count, Max, Q
from django.shortcuts import get_object_or_404, redirect
from django.views import View
from django.views.generic import ListView

from apps.accounts.models import User
from apps.bookings.models import BookingRequest
from apps.core.mixins import RoleRequiredMixin
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .forms import MessageForm
from .models import Message

PARTIES = (User.Role.PME, User.Role.TRANSPORTEUR)


class InboxView(RoleRequiredMixin, ListView):
    """All my booking threads, most recent message first, with unread counts."""

    allowed_roles = PARTIES
    template_name = "messaging/inbox.html"
    context_object_name = "threads"
    paginate_by = 20

    def get_queryset(self):
        user = self.request.user
        return (
            BookingRequest.objects.filter(Q(sender=user) | Q(receiver=user))
            .annotate(
                last_message_at=Max("messages__created_at"),
                unread=Count("messages", filter=Q(messages__read_at__isnull=True) & ~Q(messages__sender=user)),
            )
            .filter(last_message_at__isnull=False)
            .select_related("freight", "sender", "receiver")
            .order_by("-last_message_at")
        )


class MessageCreateView(RoleRequiredMixin, View):
    """POST a message into a booking thread (participants only)."""

    allowed_roles = PARTIES
    http_method_names = ["post"]

    def post(self, request, booking_pk):
        booking = get_object_or_404(BookingRequest, pk=booking_pk)
        if not booking.is_participant(request.user):
            raise PermissionDenied
        form = MessageForm(request.POST)
        if form.is_valid():
            Message.objects.create(booking=booking, sender=request.user, body=form.cleaned_data["body"])
            notify(
                booking.other_party(request.user),
                Notification.Kind.MESSAGE,
                f"Nouveau message de {request.user.display_name} (demande #{booking.pk})",
                booking.get_absolute_url() + "#messages",
            )
        else:
            messages.error(request, "Message invalide : " + " ".join(form.errors.get("body", [])))
        return redirect(booking.get_absolute_url() + "#messages")
