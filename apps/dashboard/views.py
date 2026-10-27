from django.db.models import Avg, Count, Q, Sum
from django.shortcuts import redirect
from django.views.generic import TemplateView

from apps.accounts.models import Report, User
from apps.bookings.models import BookingRequest
from apps.core.mixins import RoleRequiredMixin
from apps.core.models import AIJob
from apps.notifications.models import Notification
from apps.reviews.models import Review
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

S = BookingRequest.Status
BOOKING_RELATED = ("freight", "trip", "sender", "receiver")


def status_counts(qs):
    """Garder tous les statuts dans les indicateurs, y compris ceux dont le compte vaut zéro."""
    counts = dict(qs.values_list("status").annotate(n=Count("id")))
    return [(value, label, counts.get(value, 0)) for value, label in S.choices]


class DashboardHomeView(RoleRequiredMixin, TemplateView):
    """Routes each role to its own dashboard."""

    def get(self, request, *args, **kwargs):
        role = request.user.effective_role
        return redirect({"pme": "dashboard:pme", "transporteur": "dashboard:carrier"}.get(role, "dashboard:admin"))


class BaseDashboard(RoleRequiredMixin, TemplateView):
    def common(self, user):
        """Préparer les listes partagées en limitant les réservations à l'utilisateur connecté."""
        bookings = BookingRequest.objects.filter(Q(sender=user) | Q(receiver=user))
        return {
            "received": bookings.filter(receiver=user, status=S.PENDING).select_related(*BOOKING_RELATED)[:5],
            "sent": bookings.filter(sender=user).select_related(*BOOKING_RELATED)[:5],
            "active": bookings.filter(status__in=[S.ACCEPTED, S.IN_PROGRESS]).select_related(*BOOKING_RELATED)[:5],
            "history": bookings.filter(status__in=[S.DELIVERED, S.REFUSED, S.CANCELLED]).select_related(
                *BOOKING_RELATED
            )[:5],
            "status_counts": status_counts(bookings),
            "notifications": Notification.objects.filter(user=user)[:5],
        }


class PMEDashboardView(BaseDashboard):
    allowed_roles = (User.Role.PME,)
    template_name = "dashboard/pme.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        freights = FreightRequest.objects.filter(pme=user)
        # Les dépenses ne comptent que les livraisons terminées, pas les offres en attente ou refusées.
        delivered = BookingRequest.objects.filter(freight__pme=user, status=S.DELIVERED)
        ctx.update(self.common(user))
        ctx.update(
            freights=freights.annotate(n_bookings=Count("bookings"))[:6],
            stats={
                "annonces": freights.count(),
                "ouvertes": freights.filter(status=FreightRequest.Status.OPEN).count(),
                "livrees": delivered.count(),
                "depense": delivered.aggregate(t=Sum("proposed_price"))["t"] or 0,
            },
            to_review=delivered.filter(review__isnull=True).select_related("trip", "trip__carrier", "freight")[:5],
        )
        return ctx


class CarrierDashboardView(BaseDashboard):
    allowed_roles = (User.Role.TRANSPORTEUR,)
    template_name = "dashboard/carrier.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user = self.request.user
        trips = Trip.objects.filter(carrier=user).select_related("vehicle")
        # Le revenu affiché reflète les réservations effectivement livrées par ce transporteur.
        delivered = BookingRequest.objects.filter(trip__carrier=user, status=S.DELIVERED)
        ctx.update(self.common(user))
        ctx.update(
            trips=trips.order_by("-departure_date")[:6],
            stats={
                "trajets": trips.count(),
                "vehicules": user.vehicles.count(),
                "livrees": delivered.count(),
                "revenu": delivered.aggregate(t=Sum("proposed_price"))["t"] or 0,
            },
            profile=getattr(user, "carrier_profile", None),
        )
        return ctx


class AdminDashboardView(RoleRequiredMixin, TemplateView):
    allowed_roles = (User.Role.ADMIN,)
    template_name = "dashboard/admin.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        bookings = BookingRequest.objects.all()
        ctx.update(
            stats={
                "pme": User.objects.filter(role=User.Role.PME).count(),
                "transporteurs": User.objects.filter(role=User.Role.TRANSPORTEUR).count(),
                "annonces": FreightRequest.objects.count(),
                "trajets": Trip.objects.count(),
                "reservations": bookings.count(),
                "volume": bookings.filter(status=S.DELIVERED).aggregate(t=Sum("proposed_price"))["t"] or 0,
                "note_moyenne": Review.objects.aggregate(a=Avg("rating"))["a"],
                "signalements": Report.objects.filter(status=Report.Status.OPEN).count(),
                "drapeaux": FreightRequest.objects.filter(is_flagged=True, is_active=True).count()
                + Trip.objects.filter(is_flagged=True, is_active=True).count()
                + User.objects.filter(is_flagged=True, is_active=True).count(),
            },
            status_counts=status_counts(bookings),
            ai_stats=AIJob.objects.values("kind")
            .annotate(n=Count("id"), ok=Count("id", filter=Q(status=AIJob.Status.SUCCESS)), latency=Avg("latency_ms"))
            .order_by("kind"),
            recent_reports=Report.objects.select_related("reporter", "content_type")[:5],
        )
        return ctx
