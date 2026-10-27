from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.shortcuts import get_object_or_404, redirect
from django.utils.functional import cached_property
from django.views.generic import CreateView, ListView

from apps.accounts.models import User
from apps.bookings.models import BookingRequest
from apps.core.mixins import RoleRequiredMixin
from apps.core.tasks import start_ai_job
from apps.notifications.models import Notification
from apps.notifications.services import notify

from .forms import ReviewForm
from .models import Review
from .services import refresh_carrier_stats


class ReviewCreateView(RoleRequiredMixin, CreateView):
    """The PME rates the carrier once the booking is delivered."""

    allowed_roles = (User.Role.PME,)
    form_class = ReviewForm
    template_name = "reviews/form.html"

    @cached_property
    def booking(self):
        booking = get_object_or_404(
            BookingRequest.objects.select_related("freight", "trip", "trip__carrier"), pk=self.kwargs["booking_pk"]
        )
        if booking.freight.pme_id != self.request.user.pk:
            raise PermissionDenied("Seule la PME de cette réservation peut laisser un avis.")
        return booking

    def get(self, request, *args, **kwargs):
        if redirect_response := self._guard():
            return redirect_response
        return super().get(request, *args, **kwargs)

    def post(self, request, *args, **kwargs):
        if redirect_response := self._guard():
            return redirect_response
        return super().post(request, *args, **kwargs)

    def _guard(self):
        booking = self.booking
        if booking.status != BookingRequest.Status.DELIVERED:
            messages.error(self.request, "Vous pourrez noter le transporteur une fois la livraison effectuée.")
            return redirect(booking)
        if Review.objects.filter(booking=booking).exists():
            messages.info(self.request, "Vous avez déjà laissé un avis pour cette livraison.")
            return redirect(booking)
        return None

    def get_context_data(self, **kwargs):
        return super().get_context_data(booking=self.booking, **kwargs)

    def form_valid(self, form):
        form.instance.booking = self.booking
        form.instance.author = self.request.user
        form.instance.carrier = self.booking.trip.carrier
        review = form.save()
        refresh_carrier_stats(review.carrier)
        start_ai_job("sentiment", {"review_id": review.pk})
        notify(
            review.carrier,
            Notification.Kind.REVIEW,
            f"Nouvel avis {review.rating}/5 de {self.request.user.display_name}",
            review.carrier.get_absolute_url(),
        )
        messages.success(self.request, "Merci pour votre avis !")
        return redirect(self.booking)


class MyReviewsView(RoleRequiredMixin, ListView):
    """Carrier: reviews received. PME: reviews written."""

    allowed_roles = (User.Role.PME, User.Role.TRANSPORTEUR)
    template_name = "reviews/list.html"
    context_object_name = "reviews"
    paginate_by = 10

    def get_queryset(self):
        user = self.request.user
        qs = Review.objects.select_related("author", "carrier", "booking", "booking__freight")
        return qs.filter(carrier=user) if user.is_transporteur else qs.filter(author=user)
