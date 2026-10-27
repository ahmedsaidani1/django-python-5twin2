from django.contrib import admin

from .models import AIJob


@admin.register(AIJob)
class AIJobAdmin(admin.ModelAdmin):
    list_display = ("id", "kind", "status", "user", "provider", "latency_ms", "created_at")
    list_filter = ("kind", "status", "provider")
    search_fields = ("user__username", "error")
    readonly_fields = ("created_at", "finished_at")
    list_select_related = ("user",)
