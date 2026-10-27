from django.contrib import admin, messages
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin

from .models import CarrierProfile, CompanyProfile, Report, User


@admin.register(User)
class UserAdmin(BaseUserAdmin):
    list_display = ("username", "email", "role", "is_active", "is_flagged", "fraud_score", "date_joined")
    list_filter = ("role", "is_active", "is_flagged", "is_staff")
    fieldsets = BaseUserAdmin.fieldsets + (("CargoLink", {"fields": ("role", "phone", "is_flagged", "fraud_score")}),)
    add_fieldsets = BaseUserAdmin.add_fieldsets + (("CargoLink", {"fields": ("role", "email")}),)
    actions = ["deactivate_users", "activate_users"]

    @admin.action(description="Désactiver les comptes sélectionnés")
    def deactivate_users(self, request, queryset):
        n = queryset.exclude(pk=request.user.pk).exclude(is_superuser=True).update(is_active=False)
        self.message_user(request, f"{n} compte(s) désactivé(s).", messages.SUCCESS)

    @admin.action(description="Réactiver les comptes sélectionnés")
    def activate_users(self, request, queryset):
        n = queryset.update(is_active=True)
        self.message_user(request, f"{n} compte(s) réactivé(s).", messages.SUCCESS)


@admin.register(CompanyProfile)
class CompanyProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "city", "sector")
    list_filter = ("city",)
    search_fields = ("company_name", "user__username", "tax_id")
    list_select_related = ("user",)


@admin.register(CarrierProfile)
class CarrierProfileAdmin(admin.ModelAdmin):
    list_display = ("company_name", "user", "city", "average_rating", "reviews_count", "reputation_score")
    list_filter = ("city",)
    search_fields = ("company_name", "user__username", "license_number")
    list_select_related = ("user",)


@admin.register(Report)
class ReportAdmin(admin.ModelAdmin):
    list_display = ("__str__", "reporter", "reason", "status", "created_at")
    list_filter = ("status", "reason", "content_type")
    search_fields = ("details", "reporter__username")
    list_select_related = ("reporter", "content_type")
    actions = ["mark_resolved"]

    @admin.action(description="Marquer comme traités")
    def mark_resolved(self, request, queryset):
        queryset.update(status=Report.Status.RESOLVED, handled_by=request.user)
