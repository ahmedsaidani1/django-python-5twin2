from django import forms
from django.utils import timezone

from apps.core.forms import DateInput, StyledFormMixin

from .models import Trip, Vehicle


class VehicleForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Vehicle
        fields = ("vehicle_type", "plate_number", "capacity_kg", "capacity_m3", "refrigerated")
        widgets = {
            "capacity_kg": forms.NumberInput(attrs={"min": 50, "step": "any"}),
            "capacity_m3": forms.NumberInput(attrs={"min": 0.5, "step": "any"}),
            "plate_number": forms.TextInput(attrs={"placeholder": "123 TU 4567", "pattern": "[0-9A-Za-z \\-]{4,20}"}),
        }


class TripForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Trip
        fields = (
            "vehicle",
            "origin",
            "destination",
            "departure_date",
            "available_weight_kg",
            "available_volume_m3",
            "pricing_mode",
            "price_per_kg",
            "fixed_price",
            "notes",
        )
        widgets = {
            "departure_date": DateInput(),
            "available_weight_kg": forms.NumberInput(attrs={"min": 1, "step": "any"}),
            "available_volume_m3": forms.NumberInput(attrs={"min": 0.01, "step": "any"}),
            "price_per_kg": forms.NumberInput(attrs={"min": 0, "step": "0.001"}),
            "fixed_price": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, carrier=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["vehicle"].queryset = Vehicle.objects.filter(carrier=carrier)
        self.fields["departure_date"].widget.attrs["min"] = timezone.localdate().isoformat()

    def clean_departure_date(self):
        value = self.cleaned_data["departure_date"]
        changed = self.instance.pk is None or "departure_date" in self.changed_data
        if changed and value < timezone.localdate():
            raise forms.ValidationError("La date de départ ne peut pas être dans le passé.")
        return value

    def clean(self):
        data = super().clean()
        weight = data.get("available_weight_kg")
        if self.instance.pk and weight is not None and weight < self.instance.reserved_weight_kg:
            self.add_error("available_weight_kg", "Inférieur au poids déjà réservé sur ce trajet.")
        return data
