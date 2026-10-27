from django.urls import path

from . import views

app_name = "notifications"

urlpatterns = [
    path("", views.NotificationListView.as_view(), name="list"),
    path("<int:pk>/ouvrir/", views.NotificationOpenView.as_view(), name="open"),
    path("tout-lire/", views.NotificationMarkAllReadView.as_view(), name="mark_all_read"),
]
