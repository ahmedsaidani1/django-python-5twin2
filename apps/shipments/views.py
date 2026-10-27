from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import Q
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.models import User
from apps.core.mixins import OwnerRequiredMixin, RoleRequiredMixin
from apps.core.tasks import start_ai_job
from apps.trips.models import Trip

from .forms import FreightRequestForm, SearchForm
from .models import FreightRequest


class FreightSearchView(RoleRequiredMixin, ListView):
    """Search open annonces (used mostly by transporteurs)."""

    template_name = "shipments/list.html"
    context_object_name = "freights"
    paginate_by = 9

    def get_queryset(self):
        qs = FreightRequest.objects.open().select_related("pme", "pme__company_profile")
        self.form = SearchForm(self.request.GET or None)
        if self.form.is_valid():
            d = self.form.cleaned_data
            if d["q"]:
                qs = qs.filter(Q(title__icontains=d["q"]) | Q(description__icontains=d["q"]))
            if d["origin"]:
                qs = qs.filter(origin=d["origin"])
            if d["destination"]:
                qs = qs.filter(destination=d["destination"])
            if d["date"]:
                qs = qs.filter(pickup_date__gte=d["date"])
            if d["min_volume"] is not None:
                qs = qs.filter(volume_m3__gte=d["min_volume"])
            if d["merchandise_type"]:
                qs = qs.filter(merchandise_type=d["merchandise_type"])
        return qs.order_by("pickup_date", "-created_at")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(form=self.form, querystring=params.urlencode())
        return ctx


class MyFreightListView(RoleRequiredMixin, ListView):
    allowed_roles = (User.Role.PME,)
    template_name = "shipments/mine.html"
    context_object_name = "freights"
    paginate_by = 10

    def get_queryset(self):
        return FreightRequest.objects.filter(pme=self.request.user).prefetch_related("bookings")


class FreightDetailView(RoleRequiredMixin, DetailView):
    template_name = "shipments/detail.html"
    context_object_name = "freight"

    def get_queryset(self):
        qs = FreightRequest.objects.select_related("pme", "pme__company_profile")
        user = self.request.user
        if user.is_platform_admin:
            return qs
        return qs.filter(Q(is_active=True) | Q(pme=user))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user, freight = self.request.user, self.object
        ctx["is_owner"] = freight.pme_id == user.pk
        if ctx["is_owner"]:
            ctx["bookings"] = freight.bookings.select_related("trip", "trip__carrier", "sender")
        if user.is_transporteur:
            ctx["my_trips"] = Trip.objects.open().filter(carrier=user)
            ctx["already_sent"] = freight.bookings.filter(sender=user, status="en_attente").exists()
        return ctx


class FreightCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    allowed_roles = (User.Role.PME,)
    form_class = FreightRequestForm
    template_name = "shipments/form.html"
    success_message = "Annonce publiée avec succès."

    def get_initial(self):
        # Pre-fill from the smart-annonce AI (fields passed as query params).
        fields = FreightRequestForm.Meta.fields
        return {k: v for k, v in self.request.GET.items() if k in fields}

    def form_valid(self, form):
        form.instance.pme = self.request.user
        response = super().form_valid(form)
        start_ai_job("fraud", {"target": "annonce", "id": self.object.pk})
        return response


class FreightUpdateView(RoleRequiredMixin, OwnerRequiredMixin, SuccessMessageMixin, UpdateView):
    allowed_roles = (User.Role.PME,)
    owner_fields = ("pme",)
    model = FreightRequest
    form_class = FreightRequestForm
    template_name = "shipments/form.html"
    success_message = "Annonce mise à jour."

    def form_valid(self, form):
        if self.object.status != FreightRequest.Status.OPEN:
            messages.error(self.request, "Une annonce attribuée ou clôturée ne peut plus être modifiée.")
            return self.form_invalid(form)
        return super().form_valid(form)


class FreightDeleteView(RoleRequiredMixin, OwnerRequiredMixin, DeleteView):
    allowed_roles = (User.Role.PME,)
    owner_fields = ("pme",)
    model = FreightRequest
    template_name = "shipments/confirm_delete.html"
    success_url = reverse_lazy("shipments:mine")
    context_object_name = "freight"

    def form_valid(self, form):
        if self.object.bookings.filter(status__in=["acceptee", "en_cours"]).exists():
            messages.error(self.request, "Impossible de supprimer une annonce avec une réservation en cours.")
            return self.render_to_response(self.get_context_data())
        messages.success(self.request, "Annonce supprimée.")
        return super().form_valid(form)
