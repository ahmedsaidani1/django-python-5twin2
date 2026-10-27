from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "CargoLink — Administration"
admin.site.site_title = "CargoLink admin"
admin.site.index_title = "Modération et données"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.core.urls")),
    path("comptes/", include("apps.accounts.urls")),
    path("annonces/", include("apps.shipments.urls")),
    path("trajets/", include("apps.trips.urls")),
    path("demandes/", include("apps.bookings.urls")),
    path("messages/", include("apps.messaging.urls")),
    path("avis/", include("apps.reviews.urls")),
    path("notifications/", include("apps.notifications.urls")),
    path("tableau-de-bord/", include("apps.dashboard.urls")),
]

handler403 = "apps.core.views.error_403"
handler404 = "apps.core.views.error_404"
handler500 = "apps.core.views.error_500"
