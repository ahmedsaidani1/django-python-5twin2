from django.urls import path

from . import views

app_name = "dashboard"

urlpatterns = [
    path("", views.DashboardHomeView.as_view(), name="home"),
    path("pme/", views.PMEDashboardView.as_view(), name="pme"),
    path("transporteur/", views.CarrierDashboardView.as_view(), name="carrier"),
    path("admin/", views.AdminDashboardView.as_view(), name="admin"),
]
