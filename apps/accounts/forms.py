# Import Django's forms module to create and validate forms
from django import forms
from django.contrib.auth.forms import AuthenticationForm, PasswordResetForm, SetPasswordForm, UserCreationForm
from django.db import transaction

from apps.core.forms import StyledFormMixin

from .models import CarrierProfile, CompanyProfile, Report, User


class StyledAuthenticationForm(StyledFormMixin, AuthenticationForm):
    pass


class StyledPasswordResetForm(StyledFormMixin, PasswordResetForm):
    pass


class StyledSetPasswordForm(StyledFormMixin, SetPasswordForm):
    pass


class BaseSignupForm(StyledFormMixin, UserCreationForm):
    role: str = ""
    company_name = forms.CharField(label="Raison sociale / nom commercial", max_length=150)
    city = forms.ChoiceField(label="Ville", choices=CompanyProfile._meta.get_field("city").choices)

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ("username", "first_name", "last_name", "email", "phone")

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["email"].required = True
        self.fields["email"].widget.attrs["required"] = True
        self.fields["email"].widget.attrs["autocomplete"] = "email"

    def clean_email(self):
        email = self.cleaned_data["email"].lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError("Un compte existe déjà avec cette adresse e-mail.")
        return email

    def create_profile(self, user):
        raise NotImplementedError

    @transaction.atomic
    def save(self, commit=True):
        user = super().save(commit=False)
        user.role = self.role
        user.save()
        self.create_profile(user)
        return user


class PMESignupForm(BaseSignupForm):
    role = User.Role.PME
    sector = forms.CharField(label="Secteur d'activité", max_length=100, required=False)

    def create_profile(self, user):
        CompanyProfile.objects.create(
            user=user,
            company_name=self.cleaned_data["company_name"],
            city=self.cleaned_data["city"],
            sector=self.cleaned_data.get("sector", ""),
        )


class CarrierSignupForm(BaseSignupForm):
    role = User.Role.TRANSPORTEUR
    license_number = forms.CharField(label="N° d'autorisation de transport", max_length=50, required=False)

    def create_profile(self, user):
        CarrierProfile.objects.create(
            user=user,
            company_name=self.cleaned_data["company_name"],
            city=self.cleaned_data["city"],
            license_number=self.cleaned_data.get("license_number", ""),
        )


class UserUpdateForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = User
        fields = ("first_name", "last_name", "email", "phone")


class CompanyProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CompanyProfile
        fields = ("company_name", "sector", "city", "address", "tax_id", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class CarrierProfileForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = CarrierProfile
        fields = ("company_name", "city", "license_number", "description")
        widgets = {"description": forms.Textarea(attrs={"rows": 3})}


class ReportForm(StyledFormMixin, forms.ModelForm):
    class Meta:
        model = Report
        fields = ("reason", "details")
        widgets = {"details": forms.Textarea(attrs={"rows": 3, "maxlength": 1000})}
