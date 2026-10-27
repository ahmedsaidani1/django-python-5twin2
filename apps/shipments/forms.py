from django import forms
from django.utils import timezone

from apps.core.choices import MerchandiseType
from apps.core.forms import DateInput, StyledFormMixin
from apps.core.geo import CITY_CHOICES

from .models import FreightRequest


class FreightRequestForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = FreightRequest
        fields = (
            "title",
            "merchandise_type",
            "description",
            "weight_kg",
            "volume_m3",
            "origin",
            "destination",
            "pickup_date",
            "delivery_deadline",
            "constraints",
            "budget",
        )
        widgets = {
            "pickup_date": DateInput(),
            "delivery_deadline": DateInput(),
            "description": forms.Textarea(attrs={"rows": 3, "maxlength": 2000}),
            "weight_kg": forms.NumberInput(attrs={"min": 1, "step": "any"}),
            "volume_m3": forms.NumberInput(attrs={"min": 0.01, "step": "any"}),
            "budget": forms.NumberInput(attrs={"min": 0, "step": "0.01"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        today = timezone.localdate().isoformat()
        self.fields["pickup_date"].widget.attrs["min"] = today
        self.fields["delivery_deadline"].widget.attrs["min"] = today

    def clean_pickup_date(self):
        value = self.cleaned_data["pickup_date"]
        changed = self.instance.pk is None or "pickup_date" in self.changed_data
        if changed and value < timezone.localdate():
            raise forms.ValidationError("La date d'enlèvement ne peut pas être dans le passé.")
        return value


EMPTY = [("", "Toutes")]


class SearchForm(StyledFormMixin, forms.Form):
    """Shared GET filters for annonces and trips."""

    q = forms.CharField(label="Recherche", required=False, max_length=100)
    origin = forms.ChoiceField(label="Départ", choices=EMPTY + CITY_CHOICES, required=False)
    destination = forms.ChoiceField(label="Arrivée", choices=EMPTY + CITY_CHOICES, required=False)
    date = forms.DateField(label="À partir du", required=False, widget=DateInput())
    min_volume = forms.FloatField(
        label="Volume min. (m³)", required=False, min_value=0, widget=forms.NumberInput(attrs={"min": 0, "step": "any"})
    )
    merchandise_type = forms.ChoiceField(
        label="Type de marchandise", choices=EMPTY + list(MerchandiseType.choices), required=False
    )
