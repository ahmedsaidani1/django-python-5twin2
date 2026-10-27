from django.urls import path

from . import views

app_name = "accounts"

urlpatterns = [
    path("connexion/", views.LoginView.as_view(), name="login"),
    path("deconnexion/", views.LogoutView.as_view(), name="logout"),
    path("inscription/", views.SignupChoiceView.as_view(), name="signup"),
    path("inscription/pme/", views.PMESignupView.as_view(), name="signup_pme"),
    path("inscription/transporteur/", views.CarrierSignupView.as_view(), name="signup_carrier"),
    path("profil/", views.ProfileUpdateView.as_view(), name="profile"),
    path("transporteurs/<int:pk>/", views.CarrierPublicProfileView.as_view(), name="carrier"),
    path("mot-de-passe/oubli/", views.PasswordResetView.as_view(), name="password_reset"),
    path("mot-de-passe/envoye/", views.PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("mot-de-passe/<uidb64>/<token>/", views.PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("mot-de-passe/termine/", views.PasswordResetCompleteView.as_view(), name="password_reset_complete"),
    path("signaler/<slug:kind>/<int:pk>/", views.ReportCreateView.as_view(), name="report"),
    path("moderation/", views.ModerationView.as_view(), name="moderation"),
    path(
        "moderation/<slug:kind>/<int:pk>/<slug:action>/",
        views.ModerationActionView.as_view(),
        name="moderation_action",
    ),
]
