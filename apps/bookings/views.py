from django.contrib import messages
from django.core.exceptions import PermissionDenied
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect
from django.utils import timezone
from django.utils.functional import cached_property
from django.views import View
from django.views.generic import DetailView, FormView, ListView

from apps.accounts.models import User
from apps.core.mixins import OwnerRequiredMixin, RoleRequiredMixin
from apps.messaging.forms import MessageForm
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

from . import services
from .forms import BookingFromFreightForm, BookingFromTripForm
from .models import BookingRequest

PARTIES = (User.Role.PME, User.Role.TRANSPORTEUR)


class BookingListView(RoleRequiredMixin, ListView):
    """My requests, sent and received, filterable by status."""

    allowed_roles = PARTIES
    template_name = "bookings/list.html"
    context_object_name = "bookings"
    paginate_by = 15

    def get_queryset(self):
        user = self.request.user
        box = self.request.GET.get("box", "all")
        qs = BookingRequest.objects.select_related("freight", "trip", "trip__vehicle", "sender", "receiver")
        if box == "sent":
            qs = qs.filter(sender=user)
        elif box == "received":
            qs = qs.filter(receiver=user)
        else:
            qs = qs.filter(Q(sender=user) | Q(receiver=user))
        status = self.request.GET.get("status")
        if status in BookingRequest.Status.values:
            qs = qs.filter(status=status)
        return qs

    def get_context_data(self, **kwargs):
        return super().get_context_data(
            box=self.request.GET.get("box", "all"),
            status=self.request.GET.get("status", ""),
            statuses=BookingRequest.Status.choices,
            **kwargs,
        )


class BookingDetailView(RoleRequiredMixin, OwnerRequiredMixin, DetailView):
    """Booking page: details, status actions, status history, message thread."""

    allowed_roles = PARTIES
    owner_fields = ("sender", "receiver")
    template_name = "bookings/detail.html"
    context_object_name = "booking"
    queryset = BookingRequest.objects.select_related(
        "freight", "freight__pme", "trip", "trip__vehicle", "trip__carrier", "sender", "receiver"
    )

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        booking, user = self.object, self.request.user
        thread = booking.messages.select_related("sender")
        thread.filter(read_at__isnull=True).exclude(sender=user).update(read_at=timezone.now())
        ctx.update(
            actions=services.available_actions(booking, user),
            other_party=booking.other_party(user),
            history=booking.history.select_related("changed_by"),
            thread=thread,
            message_form=MessageForm(),
            can_review=(
                booking.status == BookingRequest.Status.DELIVERED
                and user.pk == booking.freight.pme_id
                and not hasattr(booking, "review")
            ),
        )
        return ctx


class BookingCreateFromTripView(RoleRequiredMixin, FormView):
    """PME sends a request on a carrier's trip."""

    allowed_roles = (User.Role.PME,)
    form_class = BookingFromTripForm
    template_name = "bookings/form.html"

    @cached_property
    def trip(self):
        return get_object_or_404(Trip.objects.select_related("vehicle", "carrier"), pk=self.kwargs["trip_pk"])

    def get_initial(self):
        initial = {}
        if fid := self.request.GET.get("freight"):
            initial["freight"] = fid
        return initial

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "trip": self.trip, "user": self.request.user}

    def get_context_data(self, **kwargs):
        return super().get_context_data(trip=self.trip, direction="trip", **kwargs)

    def form_valid(self, form):
        booking = services.create_booking(
            freight=form.cleaned_data["freight"],
            trip=self.trip,
            sender=self.request.user,
            message=form.cleaned_data["message"],
            proposed_price=form.cleaned_data["proposed_price"],
        )
        messages.success(self.request, "Demande envoyée au transporteur.")
        return redirect(booking)


class BookingCreateFromFreightView(RoleRequiredMixin, FormView):
    """Carrier offers one of their trips on a PME's annonce."""

    allowed_roles = (User.Role.TRANSPORTEUR,)
    form_class = BookingFromFreightForm
    template_name = "bookings/form.html"

    @cached_property
    def freight(self):
        return get_object_or_404(FreightRequest.objects.select_related("pme"), pk=self.kwargs["freight_pk"])

    def get_initial(self):
        initial = {}
        if tid := self.request.GET.get("trip"):
            initial["trip"] = tid
        return initial

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "freight": self.freight, "user": self.request.user}

    def get_context_data(self, **kwargs):
        return super().get_context_data(freight=self.freight, direction="freight", **kwargs)

    def form_valid(self, form):
        booking = services.create_booking(
            freight=self.freight,
            trip=form.cleaned_data["trip"],
            sender=self.request.user,
            message=form.cleaned_data["message"],
            proposed_price=form.cleaned_data["proposed_price"],
        )
        messages.success(self.request, "Offre envoyée à la PME.")
        return redirect(booking)


class BookingTransitionView(RoleRequiredMixin, View):
    """POST /demandes/<pk>/<action>/ — accept, refuse, cancel, start, deliver."""

    allowed_roles = PARTIES
    http_method_names = ["post"]

    def post(self, request, pk, action):
        target = services.ACTION_TARGETS.get(action)
        if target is None:
            raise Http404
        booking = get_object_or_404(BookingRequest, pk=pk)
        if not booking.is_participant(request.user):
            raise PermissionDenied
        try:
            services.transition(booking, target, request.user, note=request.POST.get("note", "")[:255])
            messages.success(request, f"Demande : {BookingRequest.Status(target).label.lower()}.")
        except services.InvalidTransition as exc:
            messages.error(request, str(exc))
        return redirect(booking)
