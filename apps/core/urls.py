from django.urls import path

from . import views

app_name = "core"

urlpatterns = [
    path("", views.HomeView.as_view(), name="home"),
    path("ai/jobs/<int:pk>/", views.AIJobDetailView.as_view(), name="ai_job"),
    path("ai/<slug:kind>/", views.AIJobCreateView.as_view(), name="ai_create"),
]
