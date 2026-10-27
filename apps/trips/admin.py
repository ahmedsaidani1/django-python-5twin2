from django.contrib import admin

from .models import Trip, Vehicle


@admin.register(Vehicle)
class VehicleAdmin(admin.ModelAdmin):
    list_display = ("plate_number", "vehicle_type", "carrier", "capacity_kg", "capacity_m3", "refrigerated")
    list_filter = ("vehicle_type", "refrigerated")
    search_fields = ("plate_number", "carrier__username")
    list_select_related = ("carrier",)


@admin.register(Trip)
class TripAdmin(admin.ModelAdmin):
    list_display = (
        "__str__",
        "carrier",
        "vehicle",
        "available_weight_kg",
        "reserved_weight_kg",
        "pricing_mode",
        "status",
        "is_active",
        "is_flagged",
    )
    list_filter = ("status", "is_active", "is_flagged", "pricing_mode", "origin", "destination")
    search_fields = ("carrier__username", "notes", "vehicle__plate_number")
    date_hierarchy = "departure_date"
    list_select_related = ("carrier", "vehicle")
    actions = ["hide"]

    @admin.action(description="Masquer les trajets sélectionnés")
    def hide(self, request, queryset):
        queryset.update(is_active=False)
