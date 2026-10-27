from django.contrib import messages
from django.contrib.messages.views import SuccessMessageMixin
from django.db.models import F, Q
from django.shortcuts import redirect
from django.urls import reverse_lazy
from django.views.generic import CreateView, DeleteView, DetailView, ListView, UpdateView

from apps.accounts.models import User
from apps.core.mixins import OwnerRequiredMixin, RoleRequiredMixin
from apps.core.tasks import start_ai_job
from apps.shipments.forms import SearchForm
from apps.shipments.models import FreightRequest

from .forms import TripForm, VehicleForm
from .models import Trip, Vehicle

CARRIER = (User.Role.TRANSPORTEUR,)


class TripSearchView(RoleRequiredMixin, ListView):
    """Search open trips with free capacity (used mostly by PME)."""

    template_name = "trips/list.html"
    context_object_name = "trips"
    paginate_by = 9

    def get_queryset(self):
        qs = Trip.objects.open().select_related("vehicle", "carrier", "carrier__carrier_profile")
        self.form = SearchForm(self.request.GET or None)
        if self.form.is_valid():
            d = self.form.cleaned_data
            if d["q"]:
                qs = qs.filter(Q(notes__icontains=d["q"]) | Q(carrier__carrier_profile__company_name__icontains=d["q"]))
            if d["origin"]:
                qs = qs.filter(origin=d["origin"])
            if d["destination"]:
                qs = qs.filter(destination=d["destination"])
            if d["date"]:
                qs = qs.filter(departure_date__gte=d["date"])
            if d["min_volume"] is not None:
                qs = qs.annotate(free_m3=F("available_volume_m3") - F("reserved_volume_m3")).filter(
                    free_m3__gte=d["min_volume"]
                )
            if d["merchandise_type"] == "frais":
                qs = qs.filter(vehicle__refrigerated=True)
        return qs.order_by("departure_date")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        params = self.request.GET.copy()
        params.pop("page", None)
        ctx.update(form=self.form, querystring=params.urlencode())
        return ctx


class MyTripListView(RoleRequiredMixin, ListView):
    allowed_roles = CARRIER
    template_name = "trips/mine.html"
    context_object_name = "trips"
    paginate_by = 10

    def get_queryset(self):
        return Trip.objects.filter(carrier=self.request.user).select_related("vehicle").order_by("-departure_date")


class TripDetailView(RoleRequiredMixin, DetailView):
    template_name = "trips/detail.html"
    context_object_name = "trip"

    def get_queryset(self):
        qs = Trip.objects.select_related("vehicle", "carrier", "carrier__carrier_profile")
        user = self.request.user
        if user.is_platform_admin:
            return qs
        return qs.filter(Q(is_active=True) | Q(carrier=user))

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        user, trip = self.request.user, self.object
        ctx["is_owner"] = trip.carrier_id == user.pk
        if ctx["is_owner"]:
            ctx["bookings"] = trip.bookings.select_related("freight", "sender")
        if user.is_pme:
            ctx["my_freights"] = FreightRequest.objects.open().filter(pme=user)
        return ctx


class TripCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    allowed_roles = CARRIER
    form_class = TripForm
    template_name = "trips/form.html"
    success_message = "Trajet publié avec succès."

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated and request.user.is_transporteur and not request.user.vehicles.exists():
            messages.info(request, "Ajoutez d'abord un véhicule avant de publier un trajet.")
            return redirect("trips:vehicle_create")
        return super().dispatch(request, *args, **kwargs)

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "carrier": self.request.user}

    def form_valid(self, form):
        form.instance.carrier = self.request.user
        response = super().form_valid(form)
        start_ai_job("fraud", {"target": "trajet", "id": self.object.pk})
        return response


class TripUpdateView(RoleRequiredMixin, OwnerRequiredMixin, SuccessMessageMixin, UpdateView):
    allowed_roles = CARRIER
    owner_fields = ("carrier",)
    model = Trip
    form_class = TripForm
    template_name = "trips/form.html"
    success_message = "Trajet mis à jour."

    def get_form_kwargs(self):
        return {**super().get_form_kwargs(), "carrier": self.request.user}


class TripDeleteView(RoleRequiredMixin, OwnerRequiredMixin, DeleteView):
    allowed_roles = CARRIER
    owner_fields = ("carrier",)
    model = Trip
    template_name = "trips/confirm_delete.html"
    success_url = reverse_lazy("trips:mine")
    context_object_name = "trip"

    def form_valid(self, form):
        if self.object.bookings.exists():
            self.object.status = Trip.Status.CANCELLED
            self.object.save(update_fields=["status"])
            messages.success(self.request, "Le trajet a des demandes : il a été annulé plutôt que supprimé.")
            return redirect(self.success_url)
        messages.success(self.request, "Trajet supprimé.")
        return super().form_valid(form)


class VehicleListView(RoleRequiredMixin, ListView):
    allowed_roles = CARRIER
    template_name = "trips/vehicles.html"
    context_object_name = "vehicles"

    def get_queryset(self):
        return Vehicle.objects.filter(carrier=self.request.user)


class VehicleCreateView(RoleRequiredMixin, SuccessMessageMixin, CreateView):
    allowed_roles = CARRIER
    form_class = VehicleForm
    template_name = "trips/vehicle_form.html"
    success_url = reverse_lazy("trips:vehicles")
    success_message = "Véhicule ajouté."

    def form_valid(self, form):
        form.instance.carrier = self.request.user
        return super().form_valid(form)


class VehicleUpdateView(RoleRequiredMixin, OwnerRequiredMixin, SuccessMessageMixin, UpdateView):
    allowed_roles = CARRIER
    owner_fields = ("carrier",)
    model = Vehicle
    form_class = VehicleForm
    template_name = "trips/vehicle_form.html"
    success_url = reverse_lazy("trips:vehicles")
    success_message = "Véhicule mis à jour."


class VehicleDeleteView(RoleRequiredMixin, OwnerRequiredMixin, DeleteView):
    allowed_roles = CARRIER
    owner_fields = ("carrier",)
    model = Vehicle
    template_name = "trips/vehicle_confirm_delete.html"
    success_url = reverse_lazy("trips:vehicles")
    context_object_name = "vehicle"

    def form_valid(self, form):
        if self.object.trips.exists():
            messages.error(self.request, "Ce véhicule est utilisé par des trajets et ne peut pas être supprimé.")
            return redirect(self.success_url)
        messages.success(self.request, "Véhicule supprimé.")
        return super().form_valid(form)
