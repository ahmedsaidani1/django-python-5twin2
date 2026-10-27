from django.urls import path

from . import views

app_name = "messaging"

urlpatterns = [
    path("", views.InboxView.as_view(), name="inbox"),
    path("demande/<int:booking_pk>/envoyer/", views.MessageCreateView.as_view(), name="send"),
]
