from django.contrib import admin

from .models import FreightRequest


@admin.register(FreightRequest)
class FreightRequestAdmin(admin.ModelAdmin):
    list_display = (
        "title",
        "pme",
        "origin",
        "destination",
        "pickup_date",
        "weight_kg",
        "status",
        "is_active",
        "is_flagged",
        "fraud_score",
    )
    list_filter = ("status", "is_active", "is_flagged", "merchandise_type", "origin", "destination")
    search_fields = ("title", "description", "pme__username")
    date_hierarchy = "pickup_date"
    list_select_related = ("pme",)
    actions = ["hide", "unflag"]

    @admin.action(description="Masquer les annonces sélectionnées")
    def hide(self, request, queryset):
        queryset.update(is_active=False)

    @admin.action(description="Valider (retirer le drapeau IA)")
    def unflag(self, request, queryset):
        queryset.update(is_flagged=False)
