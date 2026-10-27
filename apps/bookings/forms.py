from django import forms

from apps.core.forms import StyledFormMixin
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

from .models import BookingRequest


def validate_pair(freight: FreightRequest, trip: Trip):
    """Business rules shared by both booking directions. Returns a list of errors."""
    errors = []
    if freight.status != FreightRequest.Status.OPEN or not freight.is_active:
        errors.append("Cette annonce n'est plus ouverte.")
    if trip.status != Trip.Status.OPEN or not trip.is_active:
        errors.append("Ce trajet n'est plus ouvert aux réservations.")
    if not trip.can_carry(freight.weight_kg, freight.volume_m3):
        errors.append(
            f"Capacité insuffisante : il reste {trip.remaining_weight_kg:g} kg / {trip.remaining_volume_m3:g} m³ "
            f"sur ce trajet, l'annonce demande {freight.weight_kg:g} kg / {freight.volume_m3:g} m³."
        )
    # No date-window rule: the two parties agree on dates in the booking messages
    # (the matching score still ranks trips by date compatibility).
    if BookingRequest.objects.filter(freight=freight, trip=trip, status__in=BookingRequest.ACTIVE_STATUSES).exists():
        errors.append("Une demande est déjà en cours entre cette annonce et ce trajet.")
    return errors


class BaseBookingForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = BookingRequest
        fields = ("message", "proposed_price")
        widgets = {
            "message": forms.Textarea(attrs={"rows": 3, "maxlength": 1000}),
            "proposed_price": forms.NumberInput(attrs={"min": 1, "step": "0.01"}),
        }

    def get_pair(self):
        raise NotImplementedError

    def clean(self):
        data = super().clean()
        freight, trip = self.get_pair()
        if freight and trip:
            for err in validate_pair(freight, trip):
                self.add_error(None, err)
        return data


class BookingFromTripForm(BaseBookingForm):
    """PME → carrier: pick one of my open annonces to put on this trip."""

    freight = forms.ModelChoiceField(label="Mon annonce", queryset=FreightRequest.objects.none())
    field_order = ["freight", "proposed_price", "message"]

    def __init__(self, *args, trip, user, **kwargs):
        self.trip = trip
        super().__init__(*args, **kwargs)
        self.fields["freight"].queryset = FreightRequest.objects.open().filter(pme=user)

    def get_pair(self):
        return self.cleaned_data.get("freight"), self.trip


class BookingFromFreightForm(BaseBookingForm):
    """Carrier → PME: offer one of my open trips for this annonce."""

    trip = forms.ModelChoiceField(label="Mon trajet", queryset=Trip.objects.none())
    field_order = ["trip", "proposed_price", "message"]

    def __init__(self, *args, freight, user, **kwargs):
        self.freight = freight
        super().__init__(*args, **kwargs)
        self.fields["trip"].queryset = Trip.objects.open().filter(carrier=user).select_related("vehicle")

    def get_pair(self):
        return self.freight, self.cleaned_data.get("trip")
