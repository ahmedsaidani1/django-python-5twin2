from django.urls import path

from . import views

app_name = "trips"

urlpatterns = [
    path("", views.TripSearchView.as_view(), name="list"),
    path("mes-trajets/", views.MyTripListView.as_view(), name="mine"),
    path("nouveau/", views.TripCreateView.as_view(), name="create"),
    path("<int:pk>/", views.TripDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.TripUpdateView.as_view(), name="update"),
    path("<int:pk>/supprimer/", views.TripDeleteView.as_view(), name="delete"),
    path("vehicules/", views.VehicleListView.as_view(), name="vehicles"),
    path("vehicules/nouveau/", views.VehicleCreateView.as_view(), name="vehicle_create"),
    path("vehicules/<int:pk>/modifier/", views.VehicleUpdateView.as_view(), name="vehicle_update"),
    path("vehicules/<int:pk>/supprimer/", views.VehicleDeleteView.as_view(), name="vehicle_delete"),
]
