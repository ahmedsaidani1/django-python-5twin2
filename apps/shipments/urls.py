from django.urls import path

from . import views

app_name = "shipments"

urlpatterns = [
    path("", views.FreightSearchView.as_view(), name="list"),
    path("mes-annonces/", views.MyFreightListView.as_view(), name="mine"),
    path("nouvelle/", views.FreightCreateView.as_view(), name="create"),
    path("<int:pk>/", views.FreightDetailView.as_view(), name="detail"),
    path("<int:pk>/modifier/", views.FreightUpdateView.as_view(), name="update"),
    path("<int:pk>/supprimer/", views.FreightDeleteView.as_view(), name="delete"),
]
