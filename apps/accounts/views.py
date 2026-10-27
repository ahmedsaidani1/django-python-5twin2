from django.contrib import messages
from django.contrib.auth import login
from django.contrib.auth import views as auth_views
from django.contrib.contenttypes.models import ContentType
from django.core.exceptions import PermissionDenied
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse, reverse_lazy
from django.views import View
from django.views.generic import CreateView, DetailView, TemplateView

from apps.core.mixins import RoleRequiredMixin
from apps.notifications.models import Notification
from apps.notifications.services import notify
from apps.shipments.models import FreightRequest
from apps.trips.models import Trip

from .forms import (
    CarrierProfileForm,
    CarrierSignupForm,
    CompanyProfileForm,
    PMESignupForm,
    ReportForm,
    StyledAuthenticationForm,
    StyledPasswordResetForm,
    StyledSetPasswordForm,
    UserUpdateForm,
)
from .models import CarrierProfile, CompanyProfile, Report, User

ADMIN = User.Role.ADMIN


class LoginView(auth_views.LoginView):
    template_name = "accounts/login.html"
    authentication_form = StyledAuthenticationForm
    redirect_authenticated_user = True


class LogoutView(auth_views.LogoutView):
    pass


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset.html"
    email_template_name = "accounts/emails/password_reset_email.txt"
    subject_template_name = "accounts/emails/password_reset_subject.txt"
    form_class = StyledPasswordResetForm
    success_url = reverse_lazy("accounts:password_reset_done")


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    form_class = StyledSetPasswordForm
    success_url = reverse_lazy("accounts:password_reset_complete")


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"


class SignupChoiceView(TemplateView):
    template_name = "accounts/signup_choice.html"


class BaseSignupView(CreateView):
    template_name = "accounts/signup.html"
    role_label = ""

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            return redirect("dashboard:home")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(role_label=self.role_label, **kwargs)

    def form_valid(self, form):
        user = form.save()
        login(self.request, user, backend="django.contrib.auth.backends.ModelBackend")
        messages.success(self.request, "Bienvenue sur CargoLink ! Votre compte a été créé.")
        return redirect("dashboard:home")


class PMESignupView(BaseSignupView):
    form_class = PMESignupForm
    role_label = "PME / expéditeur"


class CarrierSignupView(BaseSignupView):
    form_class = CarrierSignupForm
    role_label = "transporteur"


class ProfileUpdateView(RoleRequiredMixin, View):
    """Edit the current user's account and role-specific profile."""

    allowed_roles = (User.Role.PME, User.Role.TRANSPORTEUR)
    template_name = "accounts/profile_form.html"

    def get_profile_form_class(self):
        if self.request.user.is_pme:
            return CompanyProfileForm, CompanyProfile
        return CarrierProfileForm, CarrierProfile

    def get_forms(self, data=None):
        user = self.request.user
        form_class, model = self.get_profile_form_class()
        profile = model.objects.filter(user=user).first() or model(user=user, city="Tunis")
        return UserUpdateForm(data, instance=user, prefix="user"), form_class(data, instance=profile, prefix="profile")

    def render(self, user_form, profile_form):
        return render(self.request, self.template_name, {"user_form": user_form, "profile_form": profile_form})

    def get(self, request):
        return self.render(*self.get_forms())

    def post(self, request):
        user_form, profile_form = self.get_forms(request.POST)
        if user_form.is_valid() and profile_form.is_valid():
            with transaction.atomic():
                user_form.save()
                profile_form.save()
            messages.success(request, "Profil mis à jour.")
            return redirect("accounts:profile")
        return self.render(user_form, profile_form)


class CarrierPublicProfileView(RoleRequiredMixin, DetailView):
    """Public carrier page: profile, vehicles, average rating, reviews."""

    template_name = "accounts/carrier_detail.html"
    context_object_name = "carrier"

    def get_queryset(self):
        return User.objects.filter(role=User.Role.TRANSPORTEUR, is_active=True).select_related("carrier_profile")

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        carrier = self.object
        ctx["reviews"] = carrier.reviews_received.select_related("author", "author__company_profile")[:20]
        ctx["vehicles"] = carrier.vehicles.all()
        ctx["trips"] = Trip.objects.open().filter(carrier=carrier).select_related("vehicle")[:5]
        return ctx


REPORTABLE = {"annonce": FreightRequest, "trajet": Trip, "utilisateur": User}


def _report_target(kind, pk):
    model = REPORTABLE.get(kind)
    if model is None:
        raise Http404
    return get_object_or_404(model, pk=pk)


class ReportCreateView(RoleRequiredMixin, CreateView):
    """Any signed-in user can report an annonce, a trip or a user."""

    form_class = ReportForm
    template_name = "accounts/report_form.html"

    def dispatch(self, request, *args, **kwargs):
        if request.user.is_authenticated:
            self.target = _report_target(kwargs["kind"], kwargs["pk"])
            owner = getattr(self.target, "pme", None) or getattr(self.target, "carrier", None) or self.target
            if owner == request.user:
                raise PermissionDenied("Vous ne pouvez pas signaler votre propre contenu.")
        return super().dispatch(request, *args, **kwargs)

    def get_context_data(self, **kwargs):
        return super().get_context_data(target=self.target, **kwargs)

    def form_valid(self, form):
        form.instance.reporter = self.request.user
        form.instance.content_type = ContentType.objects.get_for_model(self.target)
        form.instance.object_id = self.target.pk
        form.save()
        for admin_user in User.objects.filter(Q(role=ADMIN) | Q(is_superuser=True), is_active=True):
            notify(
                admin_user,
                Notification.Kind.MODERATION,
                f"Nouveau signalement : {form.instance}",
                reverse("accounts:moderation"),
            )
        messages.success(self.request, "Merci, votre signalement a été transmis à l'équipe de modération.")
        return redirect(self.target.get_absolute_url())


class ModerationView(RoleRequiredMixin, TemplateView):
    """Admin queue: open reports and items flagged by the fraud AI."""

    allowed_roles = (ADMIN,)
    template_name = "accounts/moderation.html"

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx["reports"] = (
            Report.objects.filter(status=Report.Status.OPEN)
            .select_related("reporter", "content_type")
            .prefetch_related("target")[:50]
        )
        ctx["flagged_freights"] = FreightRequest.objects.filter(is_flagged=True, is_active=True).select_related("pme")
        ctx["flagged_trips"] = Trip.objects.filter(is_flagged=True, is_active=True).select_related("carrier")
        ctx["flagged_users"] = User.objects.filter(is_flagged=True, is_active=True)
        return ctx


class ModerationActionView(RoleRequiredMixin, View):
    """POST actions: deactivate a user, hide/restore an annonce or trip, resolve/reject a report."""

    allowed_roles = (ADMIN,)
    http_method_names = ["post"]

    def post(self, request, kind, pk, action):
        if kind == "signalement":
            report = get_object_or_404(Report, pk=pk)
            if action not in ("traiter", "rejeter"):
                raise Http404
            report.status = Report.Status.RESOLVED if action == "traiter" else Report.Status.REJECTED
            report.handled_by = request.user
            report.save(update_fields=["status", "handled_by"])
            messages.success(request, "Signalement mis à jour.")
            return redirect("accounts:moderation")

        target = _report_target(kind, pk)
        if action == "desactiver":
            if isinstance(target, User):
                if target.pk == request.user.pk or target.is_superuser:
                    raise PermissionDenied("Impossible de désactiver ce compte.")
                target.is_active = False
                target.save(update_fields=["is_active"])
            else:
                target.is_active = False
                target.save(update_fields=["is_active"])
                owner = getattr(target, "pme", None) or getattr(target, "carrier", None)
                notify(
                    owner,
                    Notification.Kind.MODERATION,
                    f"Votre publication « {target} » a été masquée par la modération.",
                )
            messages.success(request, f"« {target} » a été désactivé(e).")
        elif action == "valider":
            target.is_flagged = False
            target.save(update_fields=["is_flagged"])
            messages.success(request, f"« {target} » a été validé(e) par la modération.")
        else:
            raise Http404
        Report.objects.filter(
            content_type=ContentType.objects.get_for_model(target), object_id=target.pk, status=Report.Status.OPEN
        ).update(status=Report.Status.RESOLVED, handled_by=request.user)
        return redirect("accounts:moderation")
