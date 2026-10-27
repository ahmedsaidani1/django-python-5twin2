from django.urls import path

from . import views

app_name = "bookings"

urlpatterns = [
    path("", views.BookingListView.as_view(), name="list"),
    path("nouvelle/trajet/<int:trip_pk>/", views.BookingCreateFromTripView.as_view(), name="create_from_trip"),
    path(
        "nouvelle/annonce/<int:freight_pk>/", views.BookingCreateFromFreightView.as_view(), name="create_from_freight"
    ),
    path("<int:pk>/", views.BookingDetailView.as_view(), name="detail"),
    path("<int:pk>/<slug:action>/", views.BookingTransitionView.as_view(), name="transition"),
]
