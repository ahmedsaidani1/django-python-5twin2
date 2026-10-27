from django.urls import path

from . import views

app_name = "reviews"

urlpatterns = [
    path("", views.MyReviewsView.as_view(), name="mine"),
    path("demande/<int:booking_pk>/noter/", views.ReviewCreateView.as_view(), name="create"),
]
